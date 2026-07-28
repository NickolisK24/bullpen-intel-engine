"""Official pitching-line repair APPLY path (2026) — one-time, fingerprint-locked.

Covers the exact-fingerprint lock and its one-character sensitivity, every pre-write
precondition, the advisory-lock contract, the strict identity/insert/update dependency order,
deferred versus existing local primary keys, the position-player and current-state safety
rules for created identities, insert and update preconditions, correction metadata and
dependent-evidence invalidation, the reviewed Brandyn Garcia line proven independently before
and after mutation, all-or-nothing rollback, the durable execution ledger and its refusal of a
second execution, the absence of any delete or current-team/roster mutation, the dispatch-only
workflow with no override inputs, and the guarantee that a failed or inconclusive result never
opens a downstream gate.
"""

from datetime import date
from pathlib import Path
import re

import pytest
import sqlalchemy as sa
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.official_pitching_line_repair_execution import (
    OfficialPitchingLineRepairExecution as Ledger,
)
from models.pitcher import Pitcher
from services import official_pitching_line_completeness_2026 as completeness
from services import official_pitching_line_repair_apply_2026 as apply_service
from services import official_pitching_line_repair_plan_2026 as planner
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = (REPO_ROOT / 'backend' / 'services'
                / 'official_pitching_line_repair_apply_2026.py')
CLI_PATH = (REPO_ROOT / 'backend' / 'scripts'
            / 'run_official_pitching_line_repair_apply_2026.py')
WORKFLOW_PATH = (REPO_ROOT / '.github' / 'workflows'
                 / 'official_pitching_line_repair_apply.yml')
PLANNER_PATH = (REPO_ROOT / 'backend' / 'services'
                / 'official_pitching_line_repair_plan_2026.py')
DECISION_RECORD = (REPO_ROOT / 'docs' / 'decisions'
                   / '2026-07-27-official-pitching-line-repair-plan.md')

SEASON = 2026
AS_OF = date(2026, 7, 25)
GDATE = date(2026, 6, 10)

# Ordinary fixture game.
GAME = 9001
HOME, AWAY = 100, 200
# Existing local identity + existing local row, values wrong => one update action.
P_UPDATE = 1
# Exact matches.
P_EXACT_A, P_EXACT_B, P_EXACT_C = 2, 5, 6
# Existing local Pitcher, no local GameLog => insertion using an existing local identity.
P_EXISTING_INSERT = 3
# No local Pitcher at all => identity creation + deferred insertion.
P_DEFERRED = 4

# The reviewed amendment line. These are the real production identifiers, so the fixture
# exercises the same key the approved contract pins.
BR_GAME = 825058
BR_PERSON = 805299
BR_TEAM = 109
BR_OPPONENT = 110
BR_LOG_ID = 43765
BR_STARTER_HOME = 8001
BR_STARTER_AWAY = 8002

LEDGER_REVISION = 'c7b3e5a91d48'


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        # The apply path requires the governed ledger revision to be the migration head.
        # A create_all schema has no alembic_version table, so the fixture states the head
        # explicitly rather than letting the precondition pass on an absent value.
        #
        # alembic_version is not part of the model metadata, so drop_test_schema does not
        # remove it. On a persistent test target (PostgreSQL) it would otherwise survive
        # into every later test in the session and accumulate a second row per run, which
        # reads as a multi-head schema and fails every migration-head guard in the suite.
        # It is therefore created empty and dropped explicitly here.
        db.session.execute(sa.text('DROP TABLE IF EXISTS alembic_version'))
        db.session.execute(sa.text(
            'CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
        db.session.execute(sa.text(
            'INSERT INTO alembic_version (version_num) VALUES (:v)'),
            {'v': LEDGER_REVISION})
        db.session.commit()
        try:
            yield flask_app
        finally:
            db.session.rollback()
            db.session.execute(sa.text('DROP TABLE IF EXISTS alembic_version'))
            db.session.commit()
            db.session.remove()
            drop_test_schema(flask_app)


# ── Official evidence fixtures ────────────────────────────────────────────────
def _ip(outs):
    return f'{outs // 3}.{outs % 3}'


def _pline(mlb_id, *, gs, outs, r=0, er=0, h=0, bb=0, k=0, hr=0):
    return (mlb_id, {'gamesStarted': gs, 'inningsPitched': _ip(outs), 'runs': r,
                     'earnedRuns': er, 'hits': h, 'baseOnBalls': bb, 'strikeOuts': k,
                     'homeRuns': hr, 'strikes': outs * 2})


def _side(team_id, lines):
    return {
        'team': {'id': team_id, 'name': f'Team{team_id}', 'abbreviation': f'T{team_id}'},
        'pitchers': [mlb_id for mlb_id, _stats in lines],
        'players': {f'ID{mlb_id}': {'person': {'id': mlb_id, 'fullName': f'P{mlb_id}'},
                                    'stats': {'pitching': stats}}
                    for mlb_id, stats in lines},
    }


def _boxscore(home, away, home_lines, away_lines):
    return {'teams': {'home': _side(home, home_lines), 'away': _side(away, away_lines)}}


def _game(game_pk, home, away, gdate=GDATE):
    return {'gamePk': game_pk, 'officialDate': gdate.isoformat(), 'gameType': 'R',
            'status': {'statusCode': 'F', 'detailedState': 'Final',
                       'abstractGameState': 'Final'},
            'teams': {'home': {'team': {'id': home, 'name': f'Team{home}',
                                        'abbreviation': f'T{home}'}},
                      'away': {'team': {'id': away, 'name': f'Team{away}',
                                        'abbreviation': f'T{away}'}}}}


def _person(mlb_id, *, name=None, position='P', throws='R'):
    return {'id': mlb_id, 'fullName': name or f'P{mlb_id}',
            'primaryPosition': {'abbreviation': position, 'code': '1', 'name': 'Pitcher'},
            'pitchHand': {'code': throws}}


HOME_LINES = [_pline(P_UPDATE, gs=1, outs=18, r=2, er=2, h=5, k=6),
              _pline(P_EXACT_A, gs=0, outs=3, r=1, er=1, h=1, k=2),
              _pline(P_EXISTING_INSERT, gs=0, outs=3, r=0, er=0, k=1)]
AWAY_LINES = [_pline(P_DEFERRED, gs=1, outs=15, r=3, er=3, h=6, k=4),
              _pline(P_EXACT_B, gs=0, outs=4, r=1, er=1, bb=1),
              _pline(P_EXACT_C, gs=0, outs=2, r=0, er=0)]
BR_HOME_LINES = [_pline(BR_STARTER_HOME, gs=1, outs=18, r=1, er=1, h=4, k=5),
                 _pline(BR_PERSON, gs=0, outs=3, r=0, er=0, h=0, k=1)]
BR_AWAY_LINES = [_pline(BR_STARTER_AWAY, gs=1, outs=21, r=2, er=2, h=7, k=8)]

PEOPLE = {mlb_id: _person(mlb_id) for mlb_id in
          (P_UPDATE, P_EXACT_A, P_EXACT_B, P_EXACT_C, P_EXISTING_INSERT, P_DEFERRED,
           BR_PERSON, BR_STARTER_HOME, BR_STARTER_AWAY)}
TEAM_REGISTRY = [{'id': tid, 'name': f'Team{tid}', 'abbreviation': f'T{tid}'}
                 for tid in (HOME, AWAY, BR_TEAM, BR_OPPONENT)]


class _FakeMlbClient:
    def __init__(self, *, people=None, boxscores=None, games=None):
        self.games = list(games if games is not None
                          else [_game(GAME, HOME, AWAY),
                                _game(BR_GAME, BR_TEAM, BR_OPPONENT)])
        self.boxscores = dict(boxscores if boxscores is not None else {
            GAME: _boxscore(HOME, AWAY, HOME_LINES, AWAY_LINES),
            BR_GAME: _boxscore(BR_TEAM, BR_OPPONENT, BR_HOME_LINES, BR_AWAY_LINES),
        })
        self.people = dict(people if people is not None else PEOPLE)

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        return [g for g in self.games if start_date <= g['officialDate'] <= end_date]

    def get_game_boxscore(self, game_pk):
        return self.boxscores.get(game_pk)

    def get_player_info(self, player_id):
        return self.people.get(player_id)

    def get_all_teams(self, sport_id=1):
        return list(TEAM_REGISTRY)


# ── Local ledger fixtures ─────────────────────────────────────────────────────
def _pitcher(mlb_id, *, name=None, position='P', active=True, team_id=None):
    existing = db.session.query(Pitcher).filter_by(mlb_id=mlb_id).first()
    if existing:
        return existing
    row = Pitcher(mlb_id=mlb_id, full_name=name or f'P{mlb_id}', position=position,
                  active=active, team_id=team_id)
    db.session.add(row)
    db.session.commit()
    return row


def _log(mlb_id, *, game_pk, team, opponent_team, gs, outs, r=0, er=0, h=0, bb=0, k=0, hr=0,
         log_id=None):
    row = _pitcher(mlb_id)
    log = GameLog(
        pitcher_id=row.id, mlb_game_pk=game_pk, game_date=GDATE, game_type='R',
        games_started=gs, innings_pitched_outs=outs, innings_pitched=(outs / 3.0),
        runs_allowed=r, earned_runs=er, hits_allowed=h, walks=bb, strikeouts=k,
        home_runs_allowed=hr, strikes=outs * 2,
        opponent=f'Team{opponent_team}', opponent_abbreviation=f'T{opponent_team}',
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_id=team, appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
    )
    if log_id is not None:
        log.id = log_id
    db.session.add(log)
    db.session.commit()
    return log


def seed_local():
    """The local ledger the reviewed manifest was planned against.

    One defective stored row, one official line with no local row but an existing local
    identity, one official line with no local identity at all, the reviewed Brandyn Garcia
    line stored with the reviewed current value, and exact matches for everything else.
    """
    # Defective: official hits are 5, the stored row says 4.
    _log(P_UPDATE, game_pk=GAME, team=HOME, opponent_team=AWAY, gs=1, outs=18, r=2, er=2,
         h=4, k=6)
    _log(P_EXACT_A, game_pk=GAME, team=HOME, opponent_team=AWAY, gs=0, outs=3, r=1, er=1,
         h=1, k=2)
    # Existing local identity, deliberately no GameLog.
    _pitcher(P_EXISTING_INSERT)
    _log(P_EXACT_B, game_pk=GAME, team=AWAY, opponent_team=HOME, gs=0, outs=4, r=1, er=1,
         bb=1)
    _log(P_EXACT_C, game_pk=GAME, team=AWAY, opponent_team=HOME, gs=0, outs=2, r=0, er=0)
    # The reviewed amendment line: official hits 0, stored 1, on the reviewed row id.
    _log(BR_PERSON, game_pk=BR_GAME, team=BR_TEAM, opponent_team=BR_OPPONENT, gs=0, outs=3,
         r=0, er=0, h=1, k=1, log_id=BR_LOG_ID)
    _log(BR_STARTER_HOME, game_pk=BR_GAME, team=BR_TEAM, opponent_team=BR_OPPONENT, gs=1,
         outs=18, r=1, er=1, h=4, k=5)
    _log(BR_STARTER_AWAY, game_pk=BR_GAME, team=BR_OPPONENT, opponent_team=BR_TEAM, gs=1,
         outs=21, r=2, er=2, h=7, k=8)


def _pin_planner_baseline(monkeypatch, plan):
    """Pin the whole V1/V2 lineage to the fixture's own observed population.

    The active baseline alone is not enough: the reviewed amendment governs a run only when
    V2 is the active acceptance AND the observed population matches it, so pinning only the
    active baseline would report the reviewed line as not-applicable instead of validated.
    The retained V1, its independent reference copy, and the amendment's own prior/amended
    populations are pinned alongside it so the lineage reconciliations stay coherent at
    fixture scale — the amendment still moves exactly one line, in exactly one direction.
    """
    observed = plan['observed_population']
    v2 = {key: observed[key] for key in planner.ACCEPTED_DEFECT_BASELINE}
    changed = planner.DEFECT_BASELINE_AMENDMENT_1['changed_fields']
    deltas = planner.DEFECT_BASELINE_AMENDMENT_1['field_deltas']
    v1 = dict(v2, **{field: v2[field] - deltas[field] for field in changed})
    amendment = dict(
        planner.DEFECT_BASELINE_AMENDMENT_1,
        prior_population={field: v1[field] for field in changed},
        amended_population={field: v2[field] for field in changed})

    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE', v2)
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE_V2', v2)
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE_V1', v1)
    monkeypatch.setattr(planner, '_AMENDMENT_V1_REFERENCE', dict(v1))
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE_VERSIONS', {'v1': v1, 'v2': v2})
    monkeypatch.setattr(planner, 'DEFECT_BASELINE_AMENDMENT_1', amendment)
    monkeypatch.setattr(planner, 'DEFECT_BASELINE_AMENDMENTS', (amendment,))
    return v2


def _plan(client=None):
    return planner.run_repair_plan(
        season=SEASON, as_of_date=AS_OF, preview_limit=0,
        client=client or _FakeMlbClient(), session=db.session)


def _fixture_contract(plan):
    """The approved execution contract for this fixture, derived from its own plan.

    Every governed value is pinned exactly as the production contract pins its own — the
    values differ, the shape and strictness do not.
    """
    counts = plan['actions_by_type']
    partition = plan['identity_resolution_partition']
    contract = dict(apply_service.APPROVED_EXECUTION_CONTRACT)
    contract.update({
        'manifest_fingerprint': plan['repair_manifest_fingerprint'],
        'action_counts': {key: counts[key] for key in planner.ACTION_TYPES},
        'total_action_count': plan['repair_manifest_action_count'],
        'defect_line_action_count': plan['defect_line_action_count'],
        'identity_partition': {
            name: partition[name] for name in
            ('missing_lines_dependent_on_identity_creation',
             'missing_lines_using_existing_identity',
             'unique_identities_requiring_creation')
        },
        'defect_population': {
            name: plan['observed_population'][name] for name in
            ('official_pitching_lines', 'exact_match_count', 'missing_line_count',
             'defective_matched_line_count', 'role_corrections_planned',
             'extra_local_line_count', 'duplicate_local_line_count',
             'appearance_team_mismatch_count', 'official_evidence_unavailable_count')
        },
    })
    return contract


@pytest.fixture
def approved(monkeypatch, app):
    """Seed the ledger, plan it, and pin the resulting plan as the approved contract."""
    seed_local()
    plan = _plan()
    _pin_planner_baseline(monkeypatch, plan)
    plan = _plan()
    assert plan['result'] == planner.RESULT_PASS, plan['decision_reasons']
    assert plan['plan_status'] == planner.PLAN_READY
    return _fixture_contract(plan)


_USE_DEFAULT_POST_COMMIT = object()


def _passing_post_commit(**kwargs):  # noqa: ARG001 — deterministic fixture, ignores inputs
    """A deterministic post-commit result in which all three governed checks pass.

    The production entrypoint always runs post-commit verification and there is no skip
    flag, so a fixture that only needs the mutation path substitutes this rather than
    standing up 30 real teams of aggregation evidence.
    """
    return {
        'checks': {name: {'passed': True, 'result': 'pass', 'exit_code': 0, 'checks': {}}
                   for name in apply_service.POST_COMMIT_CHECKS},
        'passed': True,
        'failed_checks': [],
    }


def _apply(contract, *, client=None, post_commit=_USE_DEFAULT_POST_COMMIT):
    """Run the immutable production entrypoint with fixture-scale governed constants.

    A PRIVATE TEST HELPER. The production function accepts no contract and no fingerprint —
    an approval a caller can supply is not an approval — so a fixture cannot inject one. It
    patches the module constants for the duration of the call instead, which no production
    call site can reach.

    ``post_commit`` is a test seam for the verification FUNCTION, not a skip flag: the
    default installs a deterministic passing fixture, an explicit callable installs that,
    and ``None`` leaves whatever the test has already monkeypatched in place. Post-commit
    verification runs in every one of these cases.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(apply_service, 'APPROVED_EXECUTION_CONTRACT', dict(contract))
        patch.setattr(
            apply_service,
            'APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026',
            contract['manifest_fingerprint'])
        if post_commit is _USE_DEFAULT_POST_COMMIT:
            patch.setattr(apply_service, 'run_post_commit_verification',
                          _passing_post_commit)
        elif post_commit is not None:
            patch.setattr(apply_service, 'run_post_commit_verification', post_commit)
        return apply_service.apply_reviewed_repair(
            client=client or _FakeMlbClient(), session=db.session,
            generated_at='2026-07-28T12:00:00Z')


def _counts():
    return {
        'pitchers': db.session.query(Pitcher).count(),
        'game_logs': db.session.query(GameLog).count(),
        'ledger': db.session.query(Ledger).count(),
    }


# ═══════════════ 1. The approved fingerprint is pinned exactly ══════════════
def test_the_approved_fingerprint_constant_is_the_reviewed_value():
    assert (apply_service.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026
            == '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b')
    contract = apply_service.APPROVED_EXECUTION_CONTRACT
    assert contract['manifest_fingerprint'] == (
        apply_service.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026)
    assert contract['season'] == 2026
    assert contract['as_of_date'] == '2026-07-25'
    assert contract['plan_scope'] == planner.PLAN_SCOPE_FULL
    assert contract['team_id'] is None and contract['game_pk'] is None
    assert contract['accepted_defect_baseline_version'] == 'v2'
    assert contract['prior_accepted_defect_baseline_version'] == 'v1'
    assert contract['amendment_id'] == (
        'defect_baseline_amendment_1_brandyn_garcia_hits_allowed')
    assert contract['total_action_count'] == 675
    assert contract['action_counts'] == {
        planner.ACTION_IDENTITY_CREATE: 70,
        planner.ACTION_GAME_LOG_INSERT: 445,
        planner.ACTION_GAME_LOG_UPDATE: 160,
    }
    assert contract['defect_line_action_count'] == 605
    assert contract['identity_partition'] == {
        'missing_lines_dependent_on_identity_creation': 341,
        'missing_lines_using_existing_identity': 104,
        'unique_identities_requiring_creation': 70,
    }
    assert contract['defect_population']['official_pitching_lines'] == 13301
    assert contract['defect_population']['exact_match_count'] == 12696
    assert contract['defect_population']['missing_line_count'] == 445
    assert contract['defect_population']['defective_matched_line_count'] == 160
    assert contract['amendment_action'] == {
        'stable_key': '825058:805299:109',
        'action_id': 'gamelog:update:43765:825058:805299',
        'local_game_log_id': 43765,
        'mlb_game_pk': 825058,
        'official_mlb_person_id': 805299,
        'appearance_team_id': 109,
        'field': 'hits_allowed',
        'current_value': 1,
        'proposed_value': 0,
        'reason_code': completeness.REASON_HITS_MISMATCH,
    }


def test_the_approval_lives_in_the_apply_service_and_never_in_the_read_only_planner():
    planner_text = PLANNER_PATH.read_text(encoding='utf-8')
    assert '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b' \
        not in planner_text
    assert 'APPROVED' not in planner_text
    # And the approval is a single narrowly named constant, not a reusable registry.
    text = SERVICE_PATH.read_text(encoding='utf-8')
    assert text.count(
        'APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026 = (') == 1
    for banned in ('FINGERPRINT_REGISTRY', 'APPROVED_FINGERPRINTS', 'fingerprint_allowlist',
                   'fingerprint_prefix'):
        assert banned not in text


def test_the_exact_approved_fingerprint_is_required(approved):
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS, (
        payload['decision_reasons'], payload.get('abort_detail'),
        payload['failed_preconditions'], payload.get('error_type'))
    assert payload['regenerated_manifest_fingerprint'] == approved['manifest_fingerprint']
    assert payload['transaction_committed'] is True
    assert _counts() != before


@pytest.mark.parametrize('mutate', [
    lambda f: f[:-1] + ('0' if f[-1] != '0' else '1'),
    lambda f: ('0' if f[0] != '0' else '1') + f[1:],
    lambda f: f[:32] + ('0' if f[32] != '0' else '1') + f[33:],
])
def test_a_one_character_fingerprint_difference_aborts_before_any_write(approved, mutate):
    approved['manifest_fingerprint'] = mutate(approved['manifest_fingerprint'])
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.ABORT_FINGERPRINT_MISMATCH]
    assert payload['database_writes_performed'] is False
    assert payload['transaction_committed'] is False
    assert payload['advisory_lock'] is None      # never even reached the lock
    assert _counts() == before


def test_a_fingerprint_prefix_or_similar_plan_is_not_approved(approved):
    approved['manifest_fingerprint'] = approved['manifest_fingerprint'][:32]
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['database_writes_performed'] is False


# ═══════════════ 2. Pre-write regeneration gate ═════════════════════════════
def test_a_planner_result_other_than_pass_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _degraded(**kwargs):
        plan = original(**kwargs)
        plan['result'] = planner.RESULT_INCONCLUSIVE
        plan['exit_code'] = 2
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _degraded)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.ABORT_PLAN_NOT_PASS]
    assert 'planner_result_is_pass' in payload['failed_preconditions']
    assert _counts() == before


def test_any_false_reconciliation_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _broken(**kwargs):
        plan = original(**kwargs)
        plan['reconciliations'] = dict(plan['reconciliations'])
        plan['reconciliations']['missing_lines_partition'] = False
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _broken)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert 'every_reconciliation_is_true' in payload['failed_preconditions']
    assert payload['precondition_results']['every_reconciliation_is_true']['observed'] == [
        'missing_lines_partition']
    assert _counts() == before


@pytest.mark.parametrize('action_type', list(planner.ACTION_TYPES))
def test_any_action_count_difference_aborts(approved, action_type):
    approved['action_counts'] = dict(approved['action_counts'])
    approved['action_counts'][action_type] += 1
    approved['total_action_count'] += 1
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.ABORT_PRECONDITION_FAILED]
    assert f'{action_type}_count_matches' in payload['failed_preconditions']
    assert _counts() == before


def test_a_defect_population_difference_aborts(approved):
    approved['defect_population'] = dict(approved['defect_population'])
    approved['defect_population']['exact_match_count'] += 1
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert 'defect_population_exact_match_count_matches' in payload['failed_preconditions']
    assert payload['database_writes_performed'] is False


def test_an_identity_partition_difference_aborts(approved):
    approved['identity_partition'] = dict(approved['identity_partition'])
    approved['identity_partition']['unique_identities_requiring_creation'] += 1
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert ('identity_partition_unique_identities_requiring_creation_matches'
            in payload['failed_preconditions'])


def test_baseline_version_v1_instead_of_v2_aborts(approved, monkeypatch):
    # The plan is generated against V1 as the active acceptance. The reviewed amendment is
    # part of V2's definition, so a V1 plan is not the reviewed plan.
    monkeypatch.setattr(planner, 'ACTIVE_ACCEPTED_DEFECT_BASELINE_VERSION', 'v1')
    monkeypatch.setattr(planner, 'PRIOR_ACCEPTED_DEFECT_BASELINE_VERSION', None)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert 'accepted_defect_baseline_version_is_v2' in payload['failed_preconditions']
    assert _counts() == before


def test_a_drifted_defect_baseline_aborts(approved, monkeypatch):
    drifted = dict(planner.ACCEPTED_DEFECT_BASELINE)
    drifted['official_pitching_lines'] += 1
    monkeypatch.setattr(planner, 'ACCEPTED_DEFECT_BASELINE', drifted)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert 'defect_baseline_matches_accepted_diagnostic' in payload['failed_preconditions']
    assert payload['database_writes_performed'] is False


def test_a_missing_reviewed_amendment_validation_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _missing(**kwargs):
        plan = original(**kwargs)
        plan['defect_baseline_amendment_line_validation'] = dict(
            plan['defect_baseline_amendment_line_validation'],
            status=planner.AMENDMENT_LINE_MISSING, validated=False)
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _missing)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert 'reviewed_amendment_line_status_is_validated' in payload['failed_preconditions']
    assert _counts() == before


def test_a_contradictory_reviewed_amendment_value_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _contradictory(**kwargs):
        plan = original(**kwargs)
        plan['defect_baseline_amendment_line_validation'] = dict(
            plan['defect_baseline_amendment_line_validation'], proposed_value=1)
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _contradictory)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert ('reviewed_amendment_action_matches_the_approved_record'
            in payload['failed_preconditions'])
    assert payload['database_writes_performed'] is False


def test_a_subset_scope_plan_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _scoped(**kwargs):
        plan = original(**kwargs)
        plan['plan_scope'] = planner.PLAN_SCOPE_SUBSET
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _scoped)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert 'plan_scope_is_full_season' in payload['failed_preconditions']


def test_a_wrong_migration_head_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _drifted(**kwargs):
        plan = original(**kwargs)
        plan['migration_head'] = ['deadbeef1234']
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _drifted)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert ('migration_head_is_the_governed_repair_ledger_revision'
            in payload['failed_preconditions'])
    assert _counts() == before


def test_the_ledger_migration_chains_onto_the_approved_planning_head():
    assert apply_service.APPROVED_PLANNER_MIGRATION_HEAD == 'a4f1c7e9b3d2'
    assert apply_service.REPAIR_LEDGER_MIGRATION_REVISION == LEDGER_REVISION
    assert (apply_service.REPAIR_LEDGER_MIGRATION_DOWN_REVISION
            == apply_service.APPROVED_PLANNER_MIGRATION_HEAD)


def test_every_governed_precondition_is_evaluated(approved):
    payload = _apply(approved)
    names = set(payload['precondition_results'])
    for required in (
        'planner_result_is_pass', 'planner_exit_code_is_zero', 'planner_mode_is_read_only',
        'planner_performed_no_database_writes', 'plan_scope_is_full_season',
        'plan_status_is_ready_for_apply_review', 'accepted_defect_baseline_version_is_v2',
        'prior_accepted_defect_baseline_version_is_v1',
        'defect_baseline_matches_accepted_diagnostic',
        'identity_resolution_partition_valid', 'every_reconciliation_is_true',
        'blocking_counts_by_reason_is_empty', 'duplicate_action_ids_is_empty',
        'repair_manifest_action_count_matches', 'defect_line_action_count_matches',
        'migration_head_is_the_governed_repair_ledger_revision',
        'reviewed_amendment_line_status_is_validated',
        'reviewed_amendment_line_is_required_for_scope',
        'reviewed_amendment_action_matches_the_approved_record',
        'regenerated_fingerprint_equals_the_approved_fingerprint',
    ):
        assert required in names
    assert payload['failed_preconditions'] == []


def test_the_service_offers_no_override_for_a_precondition_mismatch():
    import inspect
    signature = inspect.signature(apply_service.apply_reviewed_repair)
    # Wiring only: two artifact timestamps, the official-evidence client, the session.
    # Nothing governed, and nothing that can wave a failed precondition through.
    assert set(signature.parameters) == {
        'generated_at', 'apply_git_sha', 'client', 'session'}
    text = SERVICE_PATH.read_text(encoding='utf-8')
    for banned in ('force=', 'force:', 'override=', 'override:', 'skip_precondition',
                   'ignore_mismatch', 'allow_mismatch', 'if force', 'if override'):
        assert banned not in text.lower()
    # The failed-precondition path has exactly one outcome: return without writing.
    assert 'if failed:' in text
    assert text.count('_finalize_without_writes(payload') >= 1


# ═══════════════ 3. Advisory lock ═══════════════════════════════════════════
def test_the_advisory_lock_contract_is_dedicated_and_deterministic():
    assert apply_service.ADVISORY_LOCK_CONTRACT == (
        'official_pitching_line_repair_2026.transaction_advisory_lock')
    # Derived from the contract name, so the key is reproducible rather than a magic number.
    import hashlib
    expected = int.from_bytes(
        hashlib.sha256(apply_service.ADVISORY_LOCK_CONTRACT.encode('utf-8')).digest()[:8],
        'big', signed=True)
    assert apply_service.ADVISORY_LOCK_KEY == expected
    text = SERVICE_PATH.read_text(encoding='utf-8')
    # Transaction level, and non-blocking: a second operator is refused, never queued.
    assert 'pg_try_advisory_xact_lock' in text
    assert 'pg_advisory_lock' not in text.replace('pg_try_advisory_xact_lock', '')


def test_an_unavailable_advisory_lock_aborts_without_writes(approved, monkeypatch):
    monkeypatch.setattr(apply_service, 'acquire_repair_advisory_lock', lambda session: {
        'contract': apply_service.ADVISORY_LOCK_CONTRACT,
        'key': apply_service.ADVISORY_LOCK_KEY, 'dialect': 'postgresql',
        'status': apply_service.LOCK_UNAVAILABLE, 'acquired': False})
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.ABORT_LOCK_UNAVAILABLE]
    assert payload['database_writes_performed'] is False
    assert _counts() == before


def test_the_advisory_lock_is_acquired_before_any_mutation_precondition_is_read(approved):
    order = []
    real_lock = apply_service.acquire_repair_advisory_lock
    real_amendment = apply_service._amendment_preconditions

    def _lock(session):
        order.append('lock')
        return real_lock(session)

    def _amendment(session, update_actions, contract):
        order.append('mutation_preconditions')
        return real_amendment(session, update_actions, contract)

    apply_service.acquire_repair_advisory_lock = _lock
    apply_service._amendment_preconditions = _amendment
    try:
        payload = _apply(approved)
    finally:
        apply_service.acquire_repair_advisory_lock = real_lock
        apply_service._amendment_preconditions = real_amendment
    assert payload['result'] == apply_service.RESULT_PASS
    assert order == ['lock', 'mutation_preconditions']


def test_the_real_postgresql_advisory_lock_is_issued(app):
    if db.session.get_bind().dialect.name != 'postgresql':
        pytest.skip('transaction-level advisory locks are a PostgreSQL feature')
    lock = apply_service.acquire_repair_advisory_lock(db.session)
    assert lock['status'] == apply_service.LOCK_ACQUIRED
    assert lock['acquired'] is True
    db.session.rollback()


def test_a_non_postgresql_dialect_is_reported_distinctly_and_never_as_acquired(app):
    lock = apply_service.acquire_repair_advisory_lock(db.session)
    if db.session.get_bind().dialect.name == 'postgresql':
        assert lock['status'] == apply_service.LOCK_ACQUIRED
    else:
        assert lock['status'] == apply_service.LOCK_SINGLE_WRITER_DIALECT
        assert lock['acquired'] is False
    db.session.rollback()


# ═══════════════ 4. Dependency order ════════════════════════════════════════
def test_identities_are_created_before_insertions_and_insertions_before_updates(approved):
    order = []
    real_identities = apply_service._apply_identities
    real_inserts = apply_service._apply_insertions
    real_updates = apply_service._apply_updates

    def _identities(*args, **kwargs):
        order.append(planner.ACTION_IDENTITY_CREATE)
        return real_identities(*args, **kwargs)

    def _inserts(*args, **kwargs):
        order.append(planner.ACTION_GAME_LOG_INSERT)
        return real_inserts(*args, **kwargs)

    def _updates(*args, **kwargs):
        order.append(planner.ACTION_GAME_LOG_UPDATE)
        return real_updates(*args, **kwargs)

    apply_service._apply_identities = _identities
    apply_service._apply_insertions = _inserts
    apply_service._apply_updates = _updates
    try:
        payload = _apply(approved)
    finally:
        apply_service._apply_identities = real_identities
        apply_service._apply_insertions = real_inserts
        apply_service._apply_updates = real_updates

    assert payload['result'] == apply_service.RESULT_PASS
    # Each phase runs exactly once and the three never interleave.
    assert order == [planner.ACTION_IDENTITY_CREATE, planner.ACTION_GAME_LOG_INSERT,
                     planner.ACTION_GAME_LOG_UPDATE]


def test_a_deferred_insertion_is_written_after_its_identity_exists(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    created = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).one()
    log = (db.session.query(GameLog)
           .filter(GameLog.pitcher_id == created.id, GameLog.mlb_game_pk == GAME).one())
    assert log.appearance_team_id == AWAY


# ═══════════════ 5. Identity creation ═══════════════════════════════════════
def test_deferred_identities_use_the_newly_created_local_primary_key(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    created = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).one()
    assert payload['identity_creation_map'] == {str(P_DEFERRED): created.id}
    deferred = [r for r in payload['insertion_results']
                if r['pitcher_reference_state'] == planner.PITCHER_REFERENCE_DEFERRED]
    assert [r['local_pitcher_id'] for r in deferred] == [created.id]
    assert created.id != P_DEFERRED or created.mlb_id == P_DEFERRED


def test_existing_identities_use_the_verified_existing_local_primary_key(approved):
    existing = db.session.query(Pitcher).filter(
        Pitcher.mlb_id == P_EXISTING_INSERT).one()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    records = [r for r in payload['insertion_results']
               if r['pitcher_reference_state'] == planner.PITCHER_REFERENCE_EXISTING]
    assert [r['local_pitcher_id'] for r in records] == [existing.id]
    log = db.session.query(GameLog).filter(
        GameLog.pitcher_id == existing.id, GameLog.mlb_game_pk == GAME).one()
    assert log.appearance_team_id == HOME


def test_no_external_mlb_id_is_ever_stored_as_a_local_foreign_key(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    rows = db.session.query(GameLog, Pitcher).join(
        Pitcher, GameLog.pitcher_id == Pitcher.id).all()
    for log, pitcher in rows:
        # Every stored foreign key resolves to a Pitcher row, and that row's mlb_id is the
        # external identity. The two namespaces are never interchanged.
        assert log.pitcher_id == pitcher.id
    assert payload['verification_results'][
        'no_external_mlb_id_is_stored_as_a_local_pitcher_id'] is True


def test_a_local_primary_key_pointing_at_the_wrong_official_identity_aborts(
        approved, monkeypatch):
    original = planner.run_repair_plan
    other = None

    def _repointed(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if (action['action_type'] == planner.ACTION_GAME_LOG_INSERT
                    and action['pitcher_reference_state']
                    == planner.PITCHER_REFERENCE_EXISTING):
                action['proposed_values'] = dict(action['proposed_values'],
                                                 pitcher_id=other)
        return plan

    payload_probe = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_EXACT_A).one()
    other = payload_probe.id
    monkeypatch.setattr(planner, 'run_repair_plan', _repointed)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_IDENTITY_MISMATCH]
    assert _counts() == before


def test_a_position_player_identity_retains_its_official_position(approved):
    # Official identity evidence feeds the identity action's source fingerprint, so a
    # different official position is a different manifest. The plan is regenerated and
    # re-approved against that evidence rather than smuggled past the fingerprint gate.
    people = dict(PEOPLE)
    people[P_DEFERRED] = _person(P_DEFERRED, position='1B')
    client = _FakeMlbClient(people=people)
    contract = _fixture_contract(_plan(client))
    payload = _apply(contract, client=client)
    assert payload['result'] == apply_service.RESULT_PASS, payload['decision_reasons']
    created = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).one()
    # Appearing in a pitching section does not reclassify a position player as a pitcher.
    assert created.position == '1B'
    assert created.active is None


def test_a_created_identity_has_explicitly_null_active(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    created = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).one()
    # NULL, not the column default True: a historical appearance cannot prove current
    # activity, and every current-roster read filters active == True.
    assert created.active is None
    assert apply_service.IDENTITY_EXPLICIT_NULL_FIELDS == ('active',)


def test_a_created_identity_leaves_every_team_and_roster_field_unset(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    created = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).one()
    for field in apply_service.FORBIDDEN_IDENTITY_FIELDS:
        assert getattr(created, field, None) is None, field
    assert created.mlb_id == P_DEFERRED
    assert created.full_name == f'P{P_DEFERRED}'


def test_an_identity_created_by_another_process_after_planning_aborts(approved):
    # Simulate a concurrent identity sync landing between planning and applying.
    real_apply_identities = apply_service._apply_identities

    def _intercept(session, identity_actions, *, insert_actions_by_id):
        session.add(Pitcher(mlb_id=P_DEFERRED, full_name='concurrent', active=True))
        session.flush()
        return real_apply_identities(session, identity_actions,
                                     insert_actions_by_id=insert_actions_by_id)

    apply_service._apply_identities = _intercept
    try:
        payload = _apply(approved)
    finally:
        apply_service._apply_identities = real_apply_identities

    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.DRIFT_IDENTITY_NOW_EXISTS]
    assert payload['database_writes_performed'] is False
    # The action was NOT silently converted from deferred to existing, and the concurrent
    # row was rolled back with everything else.
    assert db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).count() == 0


def test_identity_resolution_never_consults_a_name_or_current_team():
    text = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'Pitcher.mlb_id ==' in text
    assert 'Pitcher.full_name' not in text
    assert 'Pitcher.team_id' not in text
    assert 'Pitcher.roster_status' not in text


# ═══════════════ 6. Insertion preconditions ═════════════════════════════════
def test_an_existing_game_log_for_the_stable_key_aborts(approved):
    real_apply_inserts = apply_service._apply_insertions

    def _intercept(session, insert_actions, created_ids):
        existing = session.query(Pitcher).filter(
            Pitcher.mlb_id == P_EXISTING_INSERT).one()
        session.add(GameLog(
            pitcher_id=existing.id, mlb_game_pk=GAME, game_date=GDATE, game_type='R',
            games_started=0, innings_pitched_outs=3, innings_pitched=1.0,
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
            appearance_team_id=HOME, appearance_team_source='boxscore_side',
            appearance_team_reason='appearance_team_resolved_boxscore'))
        session.flush()
        return real_apply_inserts(session, insert_actions, created_ids)

    apply_service._apply_insertions = _intercept
    try:
        payload = _apply(approved)
    finally:
        apply_service._apply_insertions = real_apply_inserts

    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.DRIFT_GAME_LOG_NOW_EXISTS]
    assert payload['database_writes_performed'] is False


def test_a_missing_insertion_precondition_aborts_the_whole_transaction(approved, monkeypatch):
    original = planner.run_repair_plan

    def _unsafe(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if action['action_type'] == planner.ACTION_GAME_LOG_INSERT:
                action['safe_to_apply'] = False
                action['blocking_reasons'] = ['official_stat_evidence_absent']
                break
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _unsafe)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_ACTION_UNSAFE]
    assert _counts() == before


def test_an_inserted_row_carries_every_proposed_field_exactly(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    created = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).one()
    log = db.session.query(GameLog).filter(
        GameLog.pitcher_id == created.id, GameLog.mlb_game_pk == GAME).one()
    # The official away starter's line, verbatim.
    assert log.games_started == 1
    assert log.innings_pitched_outs == 15
    assert log.hits_allowed == 6 and log.runs_allowed == 3 and log.earned_runs == 3
    assert log.strikeouts == 4 and log.walks == 0 and log.home_runs_allowed == 0
    assert log.strikes == 30
    assert log.game_date == GDATE and log.game_type == 'R'
    assert log.opponent == f'Team{HOME}' and log.opponent_abbreviation == f'T{HOME}'
    assert log.appearance_team_id == AWAY
    assert log.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED
    assert payload['verification_results'][
        'every_inserted_field_matches_proposed_values'] is True


def test_an_omitted_optional_field_is_written_as_null_and_never_defaulted(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    created = db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).one()
    log = db.session.query(GameLog).filter(
        GameLog.pitcher_id == created.id, GameLog.mlb_game_pk == GAME).one()
    # The fixture's official line carries none of these keys. The model defaults would have
    # invented a zero or a False; official absence must survive as NULL.
    for field in ('pitches_thrown', 'batters_faced', 'balls', 'games_finished',
                  'inherited_runners', 'inherited_runners_scored', 'save_situation',
                  'hold', 'blown_save', 'win', 'loss', 'save'):
        assert getattr(log, field) is None, field
    record = [r for r in payload['insertion_results']
              if r['local_game_log_id'] == log.id][0]
    assert 'save_situation' in record['explicitly_null_fields']


# ═══════════════ 7. Update preconditions ════════════════════════════════════
def test_a_changed_local_current_value_aborts(approved):
    real_apply_updates = apply_service._apply_updates

    def _intercept(session, update_actions, *, applied_at, operation_id):
        row = session.query(GameLog).filter(
            GameLog.mlb_game_pk == GAME,
            GameLog.appearance_team_id == HOME,
            GameLog.games_started == 1).one()
        row.hits_allowed = 99
        session.add(row)
        session.flush()
        return real_apply_updates(session, update_actions, applied_at=applied_at,
                                  operation_id=operation_id)

    apply_service._apply_updates = _intercept
    try:
        payload = _apply(approved)
    finally:
        apply_service._apply_updates = real_apply_updates

    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.DRIFT_CURRENT_VALUE_CHANGED]
    assert payload['database_writes_performed'] is False
    # The interfering write was rolled back with everything else.
    assert db.session.query(GameLog).filter(GameLog.hits_allowed == 99).count() == 0


def test_a_wrong_pitcher_mlb_id_on_the_update_target_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _wrong_identity(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if action['action_type'] == planner.ACTION_GAME_LOG_UPDATE:
                action['official_mlb_person_id'] = 999999
                break
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _wrong_identity)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] in (
        [apply_service.CONTRADICTION_IDENTITY_MISMATCH],
        [apply_service.CONTRADICTION_AMENDMENT])
    assert _counts() == before


def test_a_wrong_appearance_team_id_on_the_update_target_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _wrong_team(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if (action['action_type'] == planner.ACTION_GAME_LOG_UPDATE
                    and action['mlb_game_pk'] == GAME):
                action['official_team_id'] = 777
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _wrong_team)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_APPEARANCE_TEAM]
    assert _counts() == before


def test_an_absent_update_target_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _retargeted(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if (action['action_type'] == planner.ACTION_GAME_LOG_UPDATE
                    and action['mlb_game_pk'] == GAME):
                action['local_game_log_id'] = 987654
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _retargeted)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.DRIFT_UPDATE_TARGET_ABSENT]


def test_an_update_changes_only_its_changed_fields(approved):
    before_row = db.session.query(GameLog).filter(
        GameLog.mlb_game_pk == GAME, GameLog.appearance_team_id == HOME,
        GameLog.games_started == 1).one()
    snapshot = {c.name: getattr(before_row, c.name)
                for c in GameLog.__table__.columns}
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    after = db.session.query(GameLog).filter(GameLog.id == snapshot['id']).one()
    changed = {c.name for c in GameLog.__table__.columns
               if getattr(after, c.name) != snapshot[c.name]}
    assert changed == {'hits_allowed', 'stat_correction_count', 'last_stat_correction_at',
                       'last_stat_correction_source', 'last_stat_correction_sync_run_id'}
    assert after.hits_allowed == 5
    assert payload['verification_results'][
        'every_updated_row_left_untouched_fields_unchanged'] is True


def test_an_update_that_would_replace_a_stored_value_with_null_aborts(
        approved, monkeypatch):
    original = planner.run_repair_plan

    def _nulling(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if (action['action_type'] == planner.ACTION_GAME_LOG_UPDATE
                    and action['mlb_game_pk'] == GAME):
                action['proposed_values'] = dict(action['proposed_values'],
                                                 hits_allowed=None)
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _nulling)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_PROPOSED_NULL]
    assert _counts() == before


def test_an_update_touching_a_forbidden_identity_field_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _forbidden(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if (action['action_type'] == planner.ACTION_GAME_LOG_UPDATE
                    and action['mlb_game_pk'] == GAME):
                action['changed_fields'] = sorted(
                    set(action['changed_fields']) | {'appearance_team_id'})
                action['current_values'] = dict(action['current_values'],
                                                appearance_team_id=HOME)
                action['proposed_values'] = dict(action['proposed_values'],
                                                 appearance_team_id=AWAY)
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _forbidden)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_FORBIDDEN_FIELD]
    assert payload['database_writes_performed'] is False


def test_a_tampered_action_source_fingerprint_aborts(approved, monkeypatch):
    original = planner.run_repair_plan

    def _tampered(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if action['action_type'] == planner.ACTION_GAME_LOG_UPDATE:
                action['official_source_evidence'] = dict(
                    action['official_source_evidence'], official_name='someone else')
                break
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _tampered)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_SOURCE_FINGERPRINT]


# ═══════════════ 8. Correction metadata + dependent evidence ════════════════
def test_the_correction_count_increments_once_per_row_not_per_field(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    for record in payload['update_results']:
        row = db.session.query(GameLog).filter(
            GameLog.id == record['local_game_log_id']).one()
        assert row.stat_correction_count == 1
    assert payload['correction_metadata_results']['rows_stamped'] == len(
        payload['update_results'])


def test_correction_metadata_is_populated_on_every_updated_row(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    operation_id = payload['governed_operation_id']
    assert operation_id == int(approved['manifest_fingerprint'][:8], 16) & 0x7FFFFFFF
    assert 0 < operation_id <= 0x7FFFFFFF
    for record in payload['update_results']:
        row = db.session.query(GameLog).filter(
            GameLog.id == record['local_game_log_id']).one()
        assert row.last_stat_correction_source == 'official_pitching_line_repair'
        assert row.last_stat_correction_at is not None
        assert row.last_stat_correction_sync_run_id == operation_id
    assert apply_service.CORRECTION_SOURCE == 'official_pitching_line_repair'


def test_workload_evidence_invalidation_is_invoked_through_the_existing_contract(
        approved, monkeypatch):
    calls = []
    real = sync_service._notify_workload_evidence_game_log_correction

    def _spy(game_log, *, sync_run_id=None, strict=False):
        calls.append((game_log.id, sync_run_id, strict))
        return real(game_log, sync_run_id=sync_run_id, strict=strict)

    monkeypatch.setattr(sync_service, '_notify_workload_evidence_game_log_correction', _spy)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    updated_ids = sorted(r['local_game_log_id'] for r in payload['update_results'])
    assert sorted(log_id for log_id, _run, _strict in calls) == updated_ids
    assert {run for _log_id, run, _strict in calls} == {payload['governed_operation_id']}
    # The repair always invalidates strictly; ordinary ingestion does not.
    assert {strict for _log_id, _run, strict in calls} == {True}
    assert len(payload['dependent_evidence_invalidation_results']) == len(updated_ids)
    # The repair never fabricates replacement evidence; it only requests invalidation.
    text = SERVICE_PATH.read_text(encoding='utf-8')
    assert '_notify_workload_evidence_game_log_correction' in text


# ═══════════════ 9. The reviewed Brandyn Garcia line ════════════════════════
def test_the_reviewed_line_changes_from_one_to_zero_and_nothing_else_changes(approved):
    before = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    snapshot = {c.name: getattr(before, c.name) for c in GameLog.__table__.columns}
    assert snapshot['hits_allowed'] == 1

    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS

    after = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    assert after.hits_allowed == 0
    changed = {c.name for c in GameLog.__table__.columns
               if getattr(after, c.name) != snapshot[c.name]}
    assert changed == {'hits_allowed', 'stat_correction_count', 'last_stat_correction_at',
                       'last_stat_correction_source', 'last_stat_correction_sync_run_id'}
    assert after.stat_correction_count == snapshot['stat_correction_count'] + 1
    assert after.mlb_game_pk == BR_GAME
    assert after.appearance_team_id == BR_TEAM

    evidence = payload['reviewed_amendment_after']
    assert evidence['value_before'] == 1 and evidence['value_after'] == 0
    assert all(evidence['checks'].values())
    assert payload['reviewed_amendment_before']['stable_key'] == '825058:805299:109'


def test_a_reviewed_line_with_the_wrong_stored_value_aborts(approved):
    row = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    row.hits_allowed = 7
    db.session.add(row)
    db.session.commit()
    before = _counts()
    payload = _apply(approved)
    # The regenerated plan no longer matches the approved manifest, so nothing is written.
    assert payload['result'] in (apply_service.RESULT_INCONCLUSIVE,
                                 apply_service.RESULT_FAIL)
    assert payload['database_writes_performed'] is False
    assert _counts() == before
    assert db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one().hits_allowed == 7


def test_the_reviewed_line_is_proven_independently_inside_the_transaction(approved,
                                                                         monkeypatch):
    # The pre-write gate reads the planner's own validation object. This proves the second,
    # independent check reads the database directly: a planner claim alone is not enough.
    original = planner.run_repair_plan

    def _mislabelled(**kwargs):
        plan = original(**kwargs)
        for action in plan['repair_manifest']:
            if action.get('action_id') == (
                    apply_service.APPROVED_EXECUTION_CONTRACT[
                        'amendment_action']['action_id']):
                action['action_id'] = 'gamelog:update:43765:825058:000000'
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _mislabelled)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] in (apply_service.RESULT_FAIL,
                                 apply_service.RESULT_INCONCLUSIVE)
    assert payload['database_writes_performed'] is False
    assert _counts() == before


# ═══════════════ 10. Rollback is all-or-nothing ═════════════════════════════
def test_one_failing_action_rolls_back_every_mutation(approved, monkeypatch):
    before = _counts()
    before_hits = db.session.query(GameLog).filter(
        GameLog.id == BR_LOG_ID).one().hits_allowed

    real_verify = apply_service._verify_before_commit

    def _explode(*args, **kwargs):
        real_verify(*args, **kwargs)
        raise apply_service._Abort(apply_service.CONTRADICTION_VERIFICATION,
                                   result=apply_service.RESULT_FAIL)

    monkeypatch.setattr(apply_service, '_verify_before_commit', _explode)
    payload = _apply(approved)

    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['rollback_performed'] is True
    assert payload['transaction_committed'] is False
    assert payload['database_writes_performed'] is False
    assert _counts() == before
    assert db.session.query(GameLog).filter(
        GameLog.id == BR_LOG_ID).one().hits_allowed == before_hits


def test_zero_partial_identities_remain_after_a_rollback(approved, monkeypatch):
    identities_before = db.session.query(Pitcher).count()
    monkeypatch.setattr(
        apply_service, '_apply_insertions',
        lambda *a, **k: (_ for _ in ()).throw(
            apply_service._Abort(apply_service.CONTRADICTION_VERIFICATION,
                                 result=apply_service.RESULT_FAIL)))
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert db.session.query(Pitcher).count() == identities_before
    assert db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).count() == 0


def test_zero_partial_game_logs_remain_after_a_rollback(approved, monkeypatch):
    logs_before = db.session.query(GameLog).count()
    monkeypatch.setattr(
        apply_service, '_apply_updates',
        lambda *a, **k: (_ for _ in ()).throw(
            apply_service._Abort(apply_service.CONTRADICTION_VERIFICATION,
                                 result=apply_service.RESULT_FAIL)))
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert db.session.query(GameLog).count() == logs_before
    assert db.session.query(Ledger).count() == 0


def test_no_intermediate_commit_exists_between_the_phases(approved):
    commits = []
    real_commit = db.session.commit

    def _counted(*args, **kwargs):
        commits.append(1)
        return real_commit(*args, **kwargs)

    db.session.commit = _counted
    try:
        payload = _apply(approved)
    finally:
        db.session.commit = real_commit
    assert payload['result'] == apply_service.RESULT_PASS
    # Exactly one commit covers all 675-shaped actions plus the ledger row.
    assert len(commits) == 1


# ═══════════════ 11. Durable execution ledger ═══════════════════════════════
def test_a_successful_execution_creates_exactly_one_durable_ledger_row(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    rows = db.session.query(Ledger).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.id == payload['execution_ledger_id']
    assert row.status == 'completed'
    assert row.capability == apply_service.CAPABILITY
    assert row.approved_manifest_fingerprint == approved['manifest_fingerprint']
    assert row.regenerated_manifest_fingerprint == approved['manifest_fingerprint']
    assert row.season == 2026 and row.as_of_date == AS_OF
    assert row.accepted_baseline_version == 'v2'
    assert row.amendment_id == approved['amendment_id']
    counts = approved['action_counts']
    assert row.identity_action_count == counts[planner.ACTION_IDENTITY_CREATE]
    assert row.insert_action_count == counts[planner.ACTION_GAME_LOG_INSERT]
    assert row.update_action_count == counts[planner.ACTION_GAME_LOG_UPDATE]
    assert row.total_action_count == approved['total_action_count']
    assert row.execution_summary['governed_operation_id'] == payload[
        'governed_operation_id']


def test_a_repeated_execution_is_refused_without_writes(approved):
    first = _apply(approved)
    assert first['result'] == apply_service.RESULT_PASS
    after_first = _counts()

    second = _apply(approved)
    # A completed repair leaves a repaired ledger, so the regenerated plan is no longer the
    # approved manifest AND a completed execution row already exists. Either refusal is
    # correct; what must never happen is a second application.
    assert second['result'] == apply_service.RESULT_INCONCLUSIVE
    assert second['decision_reasons'][0] in (
        apply_service.ABORT_FINGERPRINT_MISMATCH,
        apply_service.ABORT_PRECONDITION_FAILED,
        apply_service.ABORT_ALREADY_COMPLETED)
    assert second['database_writes_performed'] is False
    assert second['transaction_committed'] is False
    assert _counts() == after_first
    assert db.session.query(Ledger).count() == 1


def test_a_preexisting_completed_ledger_row_refuses_the_repair(approved):
    db.session.add(Ledger(
        capability=apply_service.CAPABILITY,
        approved_manifest_fingerprint=approved['manifest_fingerprint'],
        regenerated_manifest_fingerprint=approved['manifest_fingerprint'],
        season=2026, as_of_date=AS_OF, accepted_baseline_version='v2',
        status='completed', identity_action_count=0, insert_action_count=0,
        update_action_count=0, total_action_count=0,
        started_at=db.func.now() if False else __import__('datetime').datetime(2026, 7, 28)))
    db.session.commit()
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [apply_service.ABORT_ALREADY_COMPLETED]
    assert _counts() == before


def test_no_ledger_row_is_stored_for_a_rolled_back_attempt(approved, monkeypatch):
    monkeypatch.setattr(
        apply_service, '_verify_before_commit',
        lambda *a, **k: (_ for _ in ()).throw(
            apply_service._Abort(apply_service.CONTRADICTION_VERIFICATION,
                                 result=apply_service.RESULT_FAIL)))
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert db.session.query(Ledger).count() == 0
    assert payload['execution_ledger_id'] is None


# ═══════════════ 12. Forbidden mutations ════════════════════════════════════
def test_no_delete_sql_is_emitted(approved):
    statements = []

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(statement)

    try:
        payload = _apply(approved)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    assert payload['result'] == apply_service.RESULT_PASS
    assert statements
    lowered = ' '.join(statements).lower()
    assert 'delete from' not in lowered
    assert 'truncate' not in lowered
    assert 'drop table' not in lowered
    assert payload['verification_results']['no_delete_occurred'] is True
    assert payload['mutation_watch']['deleted_object_count'] == 0


def test_no_delete_action_type_can_exist():
    text = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'session.delete(' not in text
    assert '.delete()' not in text
    assert 'ACTION_DELETE' not in text
    assert 'DELETE FROM' not in text.upper().replace('DELETED', '')
    assert set(planner.ACTION_TYPES) == {
        planner.ACTION_IDENTITY_CREATE, planner.ACTION_GAME_LOG_INSERT,
        planner.ACTION_GAME_LOG_UPDATE}


def test_no_current_team_or_roster_update_is_emitted(approved):
    statements = []

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(statement)

    try:
        payload = _apply(approved)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    assert payload['result'] == apply_service.RESULT_PASS
    updates = [s for s in statements if s.strip().lower().startswith('update pitchers')]
    assert updates == []
    assert payload['verification_results']['no_existing_pitcher_row_was_mutated'] is True
    assert payload['verification_results']['no_current_team_or_roster_field_changed'] is True
    assert payload['mutation_watch']['mutated_existing_pitcher_count'] == 0


def test_no_public_surface_is_modified(approved):
    statements = []

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(statement)

    try:
        payload = _apply(approved)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    assert payload['result'] == apply_service.RESULT_PASS
    lowered = ' '.join(statements).lower()
    for public_table in ('share_artifacts', 'dashboard_snapshots',
                         'team_progressive_publications', 'composed_reads',
                         'intelligence_surface_snapshots'):
        assert f'into {public_table}' not in lowered
        assert f'update {public_table}' not in lowered
    text = SERVICE_PATH.read_text(encoding='utf-8')
    # No public-surface model is imported, so none can be written.
    for banned in ('ShareArtifact', 'DashboardSnapshot', 'TeamProgressivePublication',
                   'ComposedRead', 'IntelligenceSurfaceSnapshot'):
        assert banned not in text
    # ``team_state`` appears only as the name of a gate this run keeps blocked.
    assert text.count('team_state') == text.count('team_state_performance_gate')


# ═══════════════ 13. In-transaction verification ════════════════════════════
def test_every_in_transaction_verification_is_evaluated(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    checks = payload['verification_results']
    for required in (
        'identity_actions_applied_exactly_once', 'insert_actions_applied_exactly_once',
        'update_actions_applied_exactly_once', 'total_actions_applied_exactly_once',
        'every_created_identity_has_a_real_local_primary_key',
        'every_created_identity_matches_its_reviewed_action',
        'every_inserted_game_log_matches_proposed_values',
        'every_inserted_field_matches_proposed_values',
        'every_updated_field_matches_proposed_values',
        'every_updated_row_left_untouched_fields_unchanged',
        'every_updated_row_incremented_its_correction_count_by_exactly_one',
        'every_updated_row_recorded_its_prior_correction_count',
        'every_stored_correction_count_is_exactly_one_greater',
        'every_updated_row_completed_all_dependent_evidence_families',
        'every_dependent_evidence_result_belongs_to_its_own_row',
        'every_dependent_evidence_result_carries_the_governed_operation_id',
        'every_updated_row_carries_the_governed_correction_source',
        'no_external_mlb_id_is_stored_as_a_local_pitcher_id',
        'no_duplicate_stable_game_log_key_exists', 'no_delete_occurred',
        'no_existing_pitcher_row_was_mutated',
        'no_current_team_or_roster_field_changed',
    ):
        assert checks[required] is True, required


def test_a_ledger_count_disagreeing_with_the_applied_counts_rolls_back(approved,
                                                                      monkeypatch):
    real = apply_service._apply_updates

    def _drop_one(session, update_actions, **kwargs):
        result = real(session, update_actions, **kwargs)
        result['records'] = result['records'][:-1]
        return result

    monkeypatch.setattr(apply_service, '_apply_updates', _drop_one)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_VERIFICATION]
    assert db.session.query(Ledger).count() == 0


# ═══════════════ 14. Post-commit verification ═══════════════════════════════
def test_a_post_commit_diagnostic_failure_fails_the_run_and_keeps_gates_blocked(approved):
    def _one_failing(**kwargs):  # noqa: ARG001
        return {
            'checks': {name: {'passed': name != apply_service.POST_COMMIT_CHECKS[0],
                              'result': 'fail', 'checks': {}}
                       for name in apply_service.POST_COMMIT_CHECKS},
            'passed': False,
            'failed_checks': [apply_service.POST_COMMIT_CHECKS[0]],
        }

    payload = _apply(approved, post_commit=_one_failing)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == ['post_commit_verification_failed']
    # The failing check AND the reconciliations it broke are both reported: a reader can
    # see the specific diagnostic that failed and that the run therefore did not verify.
    assert apply_service.POST_COMMIT_CHECKS[0] in payload['unresolved_issues']
    assert payload['failed_reconciliations'] == [
        'every_governed_post_commit_check_passed', 'no_post_commit_check_was_skipped']
    assert payload['post_commit_reconciliations'][
        'post_commit_verification_was_executed'] is True
    assert payload['post_commit_reconciliations'][
        'every_governed_post_commit_check_is_present'] is True
    # The commit stands: there is no automatic rollback after commit, and no retry.
    assert payload['transaction_committed'] is True
    assert payload['database_writes_performed'] is True
    for gate in apply_service.DOWNSTREAM_GATES:
        assert payload[gate] == 'blocked'


def test_a_passing_post_commit_verification_still_leaves_every_gate_blocked(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    for gate in apply_service.DOWNSTREAM_GATES:
        assert payload[gate] == 'blocked'
        assert payload['downstream_gate_statuses'][gate] == 'blocked'
    assert payload['post_commit_diagnostic_results']['passed'] is True
    assert set(payload['post_commit_aggregation_results']) == set(
        apply_service.POST_COMMIT_CHECKS[1:])


def test_there_is_no_automatic_rollback_after_commit_and_no_retry():
    text = SERVICE_PATH.read_text(encoding='utf-8')
    # Every rollback is on a pre-commit abort path. The post-commit section that follows
    # the single ``session.commit()`` contains none, so a failed post-commit check reports
    # and stops rather than silently undoing a committed repair.
    body = __import__('inspect').getsource(apply_service.apply_reviewed_repair)
    after_commit = body.split('post = run_post_commit_verification(', 1)[1]
    assert 'rollback' not in after_commit
    assert 'session.commit()' not in after_commit
    # No loop, no re-invocation, no backoff anywhere in the apply path.
    for banned in ('while true', 'for attempt', 'max_attempts', 'time.sleep', 'backoff'):
        assert banned not in text.lower()
    workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
    # No retry action, no attempt loop, no failure-swallowing step, and the apply command is
    # invoked exactly once.
    for banned in ('nick-fields/retry', 'max-attempts', 'retry-on', 'continue-on-error',
                   'while true', 'for i in', 'sleep '):
        assert banned not in workflow.lower()
    assert workflow.count('run_official_pitching_line_repair_apply_2026.py') == 1


def test_the_post_commit_checks_are_the_three_governed_read_only_checks():
    assert apply_service.POST_COMMIT_CHECKS == (
        'official_pitching_line_completeness_2026',
        'canonical_season_bullpen_aggregation_local_only',
        'canonical_season_bullpen_aggregation_official_validation',
    )


def test_post_commit_verification_reads_the_governed_thresholds(approved, monkeypatch):
    captured = {}

    def _diagnostic(**kwargs):
        captured['diagnostic'] = kwargs
        return {'result': 'pass', 'exit_code': 0, 'missing_local_line_count': 0,
                'stat_mismatch_count': 0, 'role_mismatch_count': 0,
                'extra_local_line_count': 0, 'duplicate_local_line_count': 0,
                'appearance_team_mismatch_count': 0}

    def _aggregation(**kwargs):
        official = kwargs['include_official_validation']
        return {'result': 'pass', 'exit_code': 0,
                'mode': 'official_validation' if official else 'local_only',
                'local_aggregation': {'teams_complete': 30, 'teams_partial': 0,
                                      'teams_unavailable': 0},
                'official_validation': {'teams_matched': 30,
                                        'mandatory_metric_mismatches': 0},
                'reconciliations': {'canonical_outs_match': True,
                                    'team_totals_reconcile': True,
                                    'canonical_game_grain_bullpen_outs': 12}}

    monkeypatch.setattr(completeness, 'run_diagnostic', _diagnostic)
    from services import season_bullpen_aggregation_2026 as agg
    monkeypatch.setattr(agg, 'run_aggregation', _aggregation)

    result = apply_service.run_post_commit_verification(
        season=2026, as_of_date=AS_OF, session=db.session, client=_FakeMlbClient())
    assert result['passed'] is True
    checks = result['checks']
    assert checks['official_pitching_line_completeness_2026']['checks'][
        'zero_missing_lines'] is True
    assert checks['canonical_season_bullpen_aggregation_local_only']['checks'][
        'thirty_complete_teams'] is True
    assert checks['canonical_season_bullpen_aggregation_official_validation']['checks'][
        'all_thirty_teams_matched'] is True
    assert captured['diagnostic']['season'] == 2026


@pytest.mark.parametrize('broken', [
    ('missing_local_line_count', 1),
    ('stat_mismatch_count', 1),
    ('extra_local_line_count', 1),
    ('duplicate_local_line_count', 1),
    ('appearance_team_mismatch_count', 1),
])
def test_any_nonzero_post_commit_defect_count_fails_verification(app, monkeypatch, broken):
    field, value = broken
    base = {'result': 'pass', 'exit_code': 0, 'missing_local_line_count': 0,
            'stat_mismatch_count': 0, 'role_mismatch_count': 0,
            'extra_local_line_count': 0, 'duplicate_local_line_count': 0,
            'appearance_team_mismatch_count': 0}
    base[field] = value
    monkeypatch.setattr(completeness, 'run_diagnostic', lambda **kwargs: base)
    from services import season_bullpen_aggregation_2026 as agg
    monkeypatch.setattr(agg, 'run_aggregation', lambda **kwargs: {
        'result': 'pass', 'exit_code': 0, 'mode': 'x',
        'local_aggregation': {'teams_complete': 30, 'teams_partial': 0,
                              'teams_unavailable': 0},
        'official_validation': {'teams_matched': 30, 'mandatory_metric_mismatches': 0},
        'reconciliations': {'canonical_outs_match': True}})
    result = apply_service.run_post_commit_verification(
        season=2026, as_of_date=AS_OF, session=db.session, client=_FakeMlbClient())
    assert result['passed'] is False
    assert result['failed_checks'] == ['official_pitching_line_completeness_2026']


# ═══════════════ 15. Result semantics + artifact ════════════════════════════
def test_a_failed_or_inconclusive_result_never_opens_a_downstream_gate(approved):
    approved['manifest_fingerprint'] = 'f' * 64
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_INCONCLUSIVE
    for gate in apply_service.DOWNSTREAM_GATES:
        assert payload[gate] == 'blocked'
    assert apply_service.DOWNSTREAM_GATES == (
        'foundation_3b_gate', 'public_reader_gate', 'team_state_performance_gate',
        'share_card_performance_gate', 'sc_05_gate')


def test_the_execution_artifact_carries_every_required_field(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    for field in (
        'capability', 'result', 'exit_code', 'mode', 'approved_manifest_fingerprint',
        'regenerated_manifest_fingerprint', 'artifact_input_checksum', 'git_sha',
        'migration_head', 'execution_ledger_id', 'advisory_lock', 'precondition_results',
        'action_counts_applied', 'identity_creation_map', 'insertion_results',
        'update_results', 'correction_metadata_results',
        'dependent_evidence_invalidation_results', 'reviewed_amendment_before',
        'reviewed_amendment_after', 'transaction_committed', 'database_writes_performed',
        'failed_reconciliations', 'unresolved_issues', 'downstream_gate_statuses',
    ):
        assert field in payload, field
    assert payload['mode'] == 'apply'
    assert payload['exit_code'] == 0
    assert payload['capability'] == 'official_pitching_line_repair_apply_2026_v1'
    assert payload['artifact_input_checksum'] is not None


def test_the_exit_code_vocabulary_is_governed():
    assert apply_service.EXIT_BY_RESULT == {'pass': 0, 'fail': 1, 'inconclusive': 2}


# ═══════════════ 16. Command line ═══════════════════════════════════════════
def test_the_cli_refuses_a_wrong_confirmation_before_bootstrap(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location('apply_cli', CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def _explode(*args, **kwargs):
        raise AssertionError('application bootstrap must not be reached')

    monkeypatch.setattr(module, '_failure_payload', _explode)
    output = tmp_path / 'artifact.json'
    code = module.main(['--confirm-apply', 'WRONG', '--quiet', '--output', str(output)])
    assert code == 2
    import json
    payload = json.loads(output.read_text(encoding='utf-8'))
    assert payload['result'] == 'inconclusive'
    assert payload['decision_reasons'] == ['confirmation_phrase_mismatch']
    assert payload['database_writes_performed'] is False
    for gate in ('foundation_3b_gate', 'public_reader_gate', 'sc_05_gate'):
        assert payload[gate] == 'blocked'


def test_the_cli_confirmation_phrase_matches_the_service():
    text = CLI_PATH.read_text(encoding='utf-8')
    assert "CONFIRMATION_PHRASE = 'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06'" in text
    assert apply_service.CONFIRMATION_PHRASE == 'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06'
    # Confirmation is checked before the application import, so a wrong phrase never opens
    # a database connection.
    confirm_index = text.index("if args.confirm_apply != CONFIRMATION_PHRASE:")
    import_index = text.index('from app import app')
    assert confirm_index < import_index


def test_the_cli_exposes_no_scope_fingerprint_or_override_input():
    text = CLI_PATH.read_text(encoding='utf-8')
    for banned in ('--season', '--as-of-date', '--team-id', '--game-pk', '--fingerprint',
                   '--force', '--override', '--plan-scope', '--action-count',
                   '--accept-fingerprint'):
        assert banned not in text
    assert text.count("'--confirm-apply'") == 1
    # Only three other arguments exist and none of them selects what runs.
    assert sorted(re.findall(r"add_argument\(\s*'(--[a-z-]+)'", text)) == [
        '--compact', '--confirm-apply', '--output', '--quiet']


# ═══════════════ 17. Workflow ═══════════════════════════════════════════════
def test_the_apply_workflow_is_dispatch_only():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in text
    for banned in ('schedule:', 'on: push', 'push:', 'pull_request:', 'repository_dispatch:',
                   'workflow_call:', 'workflow_run:'):
        assert banned not in text


def test_the_apply_workflow_takes_only_the_confirmation_input():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06' in text
    inputs_block = text.split('inputs:', 1)[1].split('concurrency:', 1)[0]
    assert 'confirm_apply:' in inputs_block
    for banned in ('season:', 'as_of_date:', 'team_id:', 'game_pk:', 'plan_scope:',
                   'preview_limit:', 'fingerprint:', 'manifest_fingerprint:',
                   'action_count:', 'force:', 'override:'):
        assert banned not in inputs_block
    # Exactly one dispatch input exists.
    assert len(re.findall(r'^      [a-z_]+:$', inputs_block, re.M)) == 1


def _apply_job_steps():
    """The ordered step bodies of ``jobs.apply.steps``, parsed positionally.

    Deliberately dependency-free: PyYAML is not in backend/requirements.txt, so a test that
    imported it would pass here and fail in CI. The workflow's list structure is regular
    enough to walk directly, and walking it is what makes the ordering claim a POSITION
    comparison rather than a substring comparison — the previous version of this test
    compared character offsets in the raw file, which is satisfied by any order at all as
    long as the strings appear in the right sequence in the text.
    """
    lines = WORKFLOW_PATH.read_text(encoding='utf-8').splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith('  apply:'):
            start = index
            break
    assert start is not None, 'jobs.apply is missing'

    steps_at = None
    for index in range(start + 1, len(lines)):
        if lines[index].startswith('    steps:'):
            steps_at = index
            break
        if lines[index].strip() and not lines[index].startswith('    '):
            break
    assert steps_at is not None, 'jobs.apply.steps is missing'

    steps, current = [], None
    for line in lines[steps_at + 1:]:
        if line.strip() and not line.startswith('    '):
            break                                   # left the job block entirely
        if line.startswith('      - '):
            if current is not None:
                steps.append('\n'.join(current))
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        steps.append('\n'.join(current))
    assert steps, 'jobs.apply.steps is empty'
    return steps


def _step_index(steps, marker):
    matches = [index for index, body in enumerate(steps) if marker in body]
    assert len(matches) == 1, f'expected exactly one step matching {marker!r}, got {matches}'
    return matches[0]


def test_the_apply_workflow_validates_confirmation_before_any_database_step():
    steps = _apply_job_steps()

    confirm = _step_index(steps, 'name: Validate apply confirmation')
    checkout = _step_index(steps, 'uses: actions/checkout')
    setup_python = _step_index(steps, 'uses: actions/setup-python')
    install = _step_index(steps, 'pip install -r backend/requirements.txt')
    apply_command = _step_index(steps, 'run_official_pitching_line_repair_apply_2026.py')
    upload = _step_index(steps, 'uses: actions/upload-artifact')

    # Confirmation runs before anything that fetches code, installs a runtime, or could
    # reach a database. The confirmation step needs no repository file, so it can and must
    # run ahead of checkout.
    assert confirm < checkout
    assert confirm < setup_python
    assert confirm < install
    assert confirm < apply_command

    # It is literally the first item under jobs.apply.steps, not merely early.
    assert confirm == 0

    # The governed order, end to end.
    assert [confirm, checkout, setup_python, install, apply_command, upload] == [
        0, 1, 2, 3, 4, 5]

    # Nothing precedes confirmation, and if a step ever were inserted ahead of it, none of
    # these could appear in it.
    database_capable = ('actions/checkout', 'actions/setup-python', 'pip install',
                        'python ', 'flask ', 'psql', 'alembic', '$DATABASE_URL',
                        'DATABASE_URL: ')
    for body in steps[:confirm]:
        for token in database_capable:
            assert token not in body, token

    # The confirmation step also proves the production secrets are present, so a dispatch
    # with a correct phrase and a missing secret stops at the same point.
    assert 'Missing required production repository secret' in steps[confirm]
    assert 'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06' in steps[confirm]


def test_the_apply_workflow_runs_checkout_and_the_apply_command_exactly_once():
    steps = _apply_job_steps()
    assert sum(1 for body in steps if 'uses: actions/checkout' in body) == 1
    assert sum(1 for body in steps
               if 'run_official_pitching_line_repair_apply_2026.py' in body) == 1
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert text.count('actions/checkout') == 1
    assert text.count('run_official_pitching_line_repair_apply_2026.py') == 1


def test_the_apply_workflow_declares_no_scope_fingerprint_or_override_input():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    inputs_block = text.split('inputs:', 1)[1].split('concurrency:', 1)[0]
    for banned in ('fingerprint', 'manifest_fingerprint', 'override', 'force', 'season',
                   'as_of_date', 'date', 'team_id', 'team', 'game_pk', 'game',
                   'plan_scope', 'scope', 'action_count', 'preview_limit'):
        assert banned not in inputs_block, banned
    assert 'confirm_apply:' in inputs_block


def test_the_apply_workflow_is_serialized_and_never_cancelled():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'group: official-pitching-line-repair-apply-2026' in text
    assert 'cancel-in-progress: false' in text
    assert 'permissions:' in text and 'contents: read' in text


def test_the_apply_workflow_uploads_a_private_thirty_day_artifact():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'retention-days: 30' in text
    assert 'if-no-files-found: error' in text
    # Private by default: artifacts are private unless published, and nothing here
    # publishes one or echoes an environment value.
    for banned in ('gh release', 'gh api', 'actions/github-script',
                   'echo "$DATABASE_URL"', 'echo $DATABASE_URL', 'env | ', 'printenv',
                   'echo "$SECRET_KEY"', 'set -x'):
        assert banned not in text


def test_the_apply_workflow_validates_production_secrets():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'Missing required production repository secret' in text
    assert 'secrets.DATABASE_URL' in text
    assert 'secrets.SECRET_KEY' in text


def test_the_apply_workflow_runs_post_commit_verification_and_keeps_gates_blocked():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'post_commit_verification' in text
    assert 'foundation_3b_gate' in text
    assert 'Foundation 3B is not activated by a successful apply' in text


# ═══════════════ 18. Documentation ══════════════════════════════════════════
def test_the_decision_record_documents_the_execution_contract():
    text = DECISION_RECORD.read_text(encoding='utf-8')
    for required in (
        '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b',
        'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06',
        'pg_try_advisory_xact_lock',
        'official_pitching_line_repair_executions',
        'c7b3e5a91d48',
    ):
        assert required in text, required


# ═══════════════ 19. The production entrypoint is immutable ═════════════════
def test_the_production_entrypoint_accepts_no_governed_parameter():
    import inspect
    parameters = inspect.signature(apply_service.apply_reviewed_repair).parameters
    assert set(parameters) == {'generated_at', 'apply_git_sha', 'client', 'session'}
    # Every one is keyword-only wiring, and none is governed.
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    for banned in ('contract', 'approved_fingerprint', 'fingerprint',
                   'manifest_fingerprint', 'action_counts', 'total_action_count',
                   'season', 'as_of_date', 'date', 'team_id', 'game_pk', 'plan_scope',
                   'scope', 'amendment', 'amendment_id', 'migration_head',
                   'run_post_commit', 'skip_post_commit', 'skip_verification',
                   'force', 'override', 'allow'):
        assert banned not in parameters, banned


def test_the_entrypoint_reads_the_governed_values_from_the_module_constants():
    import inspect
    body = inspect.getsource(apply_service.apply_reviewed_repair)
    assert 'contract = dict(APPROVED_EXECUTION_CONTRACT)' in body
    assert ('approved_fingerprint = '
            'APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026') in body
    # Neither name is ever taken from a parameter or a default.
    assert 'contract or ' not in body
    assert 'approved_fingerprint or ' not in body


def test_no_other_public_function_accepts_an_alternate_approval():
    import inspect
    for name, member in vars(apply_service).items():
        if name.startswith('_') or not inspect.isfunction(member):
            continue
        if getattr(member, '__module__', None) != apply_service.__name__:
            continue
        parameters = set(inspect.signature(member).parameters)
        for banned in ('contract', 'approved_fingerprint', 'manifest_fingerprint',
                       'action_counts', 'plan_scope', 'amendment_id'):
            assert banned not in parameters, f'{name} accepts {banned}'


def test_a_caller_cannot_execute_a_different_fingerprint_by_passing_arguments(approved):
    import inspect
    parameters = inspect.signature(apply_service.apply_reviewed_repair).parameters
    # There is no argument to pass. The only reachable lever is the module constant, which
    # a production call site cannot touch.
    assert 'approved_fingerprint' not in parameters
    with pytest.raises(TypeError):
        apply_service.apply_reviewed_repair(
            approved_fingerprint='f' * 64, session=db.session, client=_FakeMlbClient())
    with pytest.raises(TypeError):
        apply_service.apply_reviewed_repair(
            contract=dict(approved), session=db.session, client=_FakeMlbClient())
    assert _counts()['ledger'] == 0


def test_a_caller_cannot_execute_a_different_season_scope_count_or_amendment(approved):
    for governed in ({'season': 2025}, {'as_of_date': '2026-08-01'},
                     {'plan_scope': planner.PLAN_SCOPE_SUBSET}, {'team_id': 109},
                     {'game_pk': 825058}, {'total_action_count': 999},
                     {'amendment_id': 'something_else'}):
        with pytest.raises(TypeError):
            apply_service.apply_reviewed_repair(
                session=db.session, client=_FakeMlbClient(), **governed)
    assert _counts()['ledger'] == 0


def test_a_contract_whose_fingerprint_disagrees_with_the_constant_aborts(approved):
    # The two halves of the approval must agree. A contract restating a different
    # fingerprint means one of them was edited alone.
    drifted = dict(approved, manifest_fingerprint='a' * 64)
    before = _counts()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(apply_service, 'APPROVED_EXECUTION_CONTRACT', drifted)
        patch.setattr(
            apply_service,
            'APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026',
            approved['manifest_fingerprint'])
        payload = apply_service.apply_reviewed_repair(
            session=db.session, client=_FakeMlbClient())
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [
        apply_service.CONTRADICTION_APPROVAL_CONTRACT_DRIFT]
    assert payload['database_writes_performed'] is False
    assert _counts() == before


def test_the_cli_calls_the_immutable_production_entrypoint():
    text = CLI_PATH.read_text(encoding='utf-8')
    assert 'apply_service.apply_reviewed_repair(' in text
    call = text.split('apply_service.apply_reviewed_repair(', 1)[1].split(')', 1)[0]
    # Only wiring crosses the boundary.
    assert 'generated_at=' in call
    assert 'apply_git_sha=' in call
    for banned in ('contract=', 'approved_fingerprint=', 'fingerprint=',
                   'run_post_commit=', 'season=', 'as_of_date=', 'team_id=', 'game_pk='):
        assert banned not in call, banned


# ═══════════════ 20. Post-commit verification cannot be skipped ═════════════
def test_post_commit_verification_always_runs_after_a_successful_commit(approved):
    calls = []

    def _observed(**kwargs):
        calls.append(kwargs)
        return _passing_post_commit()

    payload = _apply(approved, post_commit=_observed)
    assert payload['result'] == apply_service.RESULT_PASS
    assert len(calls) == 1
    assert calls[0]['season'] == approved['season']
    assert payload['post_commit_reconciliations'] == {
        name: True for name in apply_service.POST_COMMIT_RECONCILIATIONS}


def test_pass_is_impossible_when_post_commit_verification_is_absent(approved):
    payload = _apply(approved, post_commit=lambda **kwargs: None)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == ['post_commit_verification_failed']
    assert payload['post_commit_reconciliations'][
        'post_commit_verification_was_executed'] is False
    # The commit still stands — there is no automatic rollback after commit.
    assert payload['transaction_committed'] is True
    for gate in apply_service.DOWNSTREAM_GATES:
        assert payload[gate] == 'blocked'


def test_pass_is_impossible_when_post_commit_verification_raises(approved):
    def _explodes(**kwargs):  # noqa: ARG001
        raise RuntimeError('diagnostic unavailable')

    payload = _apply(approved, post_commit=_explodes)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['error_type'] == 'RuntimeError'
    assert payload['post_commit_reconciliations'][
        'post_commit_verification_was_executed'] is False


def test_pass_is_impossible_when_one_governed_post_commit_check_is_missing(approved):
    def _incomplete(**kwargs):  # noqa: ARG001
        names = apply_service.POST_COMMIT_CHECKS[:-1]
        return {'checks': {n: {'passed': True, 'result': 'pass', 'checks': {}}
                           for n in names},
                'passed': True, 'failed_checks': []}

    payload = _apply(approved, post_commit=_incomplete)
    assert payload['result'] == apply_service.RESULT_FAIL
    reconciliations = payload['post_commit_reconciliations']
    assert reconciliations['post_commit_verification_was_executed'] is True
    assert reconciliations['every_governed_post_commit_check_is_present'] is False
    assert reconciliations['no_post_commit_check_was_skipped'] is False
    assert apply_service.POST_COMMIT_CHECKS[-1] in payload['unresolved_issues']


@pytest.mark.parametrize('failing_index', [0, 1, 2])
def test_pass_is_impossible_when_one_governed_post_commit_check_fails(
        approved, failing_index):
    failing = apply_service.POST_COMMIT_CHECKS[failing_index]

    def _one_failing(**kwargs):  # noqa: ARG001
        return {'checks': {n: {'passed': n != failing, 'result': 'pass', 'checks': {}}
                           for n in apply_service.POST_COMMIT_CHECKS},
                'passed': False, 'failed_checks': [failing]}

    payload = _apply(approved, post_commit=_one_failing)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['post_commit_reconciliations'][
        'every_governed_post_commit_check_passed'] is False
    assert failing in payload['unresolved_issues']
    for gate in apply_service.DOWNSTREAM_GATES:
        assert payload[gate] == 'blocked'


def test_the_governed_post_commit_reconciliation_names_are_pinned():
    assert apply_service.POST_COMMIT_RECONCILIATIONS == (
        'post_commit_verification_was_executed',
        'every_governed_post_commit_check_is_present',
        'every_governed_post_commit_check_passed',
        'no_post_commit_check_was_skipped',
    )


# ═══════════════ 21. Strict dependent-evidence invalidation ═════════════════
def _marker_names():
    return (('services.workload_recovery_evidence',
             'mark_game_log_correction_for_workload_recovery',
             sync_service.EVIDENCE_FAMILY_WORKLOAD),
            ('services.appearance_context_evidence',
             'mark_game_log_correction_for_appearance_context',
             sync_service.EVIDENCE_FAMILY_APPEARANCE_CONTEXT),
            ('services.inherited_traffic_evidence',
             'mark_game_log_correction_for_inherited_traffic',
             sync_service.EVIDENCE_FAMILY_INHERITED_TRAFFIC))


def _break_marker(monkeypatch, module_name, function_name, behaviour):
    module = __import__(module_name, fromlist=[function_name])
    monkeypatch.setattr(module, function_name, behaviour)


def test_ordinary_ingestion_keeps_best_effort_invalidation(app, monkeypatch):
    # A daily sync must not stop ingesting official corrections because an evidence table
    # is momentarily unhappy. The default is unchanged, and its return shape is unchanged.
    _break_marker(monkeypatch, 'services.workload_recovery_evidence',
                  'mark_game_log_correction_for_workload_recovery',
                  lambda *a, **k: (_ for _ in ()).throw(RuntimeError('evidence down')))
    seed_local()
    log = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    result = sync_service._notify_workload_evidence_game_log_correction(log)
    assert set(result) == {'marked_count', 'evidence_ids'}
    assert result['marked_count'] == 0


def test_strict_invalidation_reports_all_three_governed_families(app):
    seed_local()
    log = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    result = sync_service._notify_workload_evidence_game_log_correction(
        log, sync_run_id=4242, strict=True)
    assert sorted(result['families']) == sorted(sync_service.REQUIRED_EVIDENCE_FAMILIES)
    assert all(item['status'] == 'completed' for item in result['families'].values())
    assert result['all_required_families_completed'] is True
    assert result['failed_families'] == []
    assert result['game_log_id'] == BR_LOG_ID
    assert result['sync_run_id'] == 4242


def test_a_successful_zero_mark_result_is_accepted_not_treated_as_a_failure(app):
    # A corrected line with no dependent evidence is ordinary. Zero marked rows is a
    # completed invalidation, not an exception.
    seed_local()
    log = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    result = sync_service._notify_workload_evidence_game_log_correction(
        log, sync_run_id=1, strict=True)
    assert result['marked_count'] == 0
    assert result['all_required_families_completed'] is True
    for family in result['families'].values():
        assert family['status'] == 'completed'
        assert family['marked_count'] == 0


@pytest.mark.parametrize('module_name,function_name,family', list(_marker_names()))
def test_an_invalidation_exception_rolls_back_every_action(
        approved, monkeypatch, module_name, function_name, family):
    before = _counts()
    before_hits = db.session.query(GameLog).filter(
        GameLog.id == BR_LOG_ID).one().hits_allowed
    _break_marker(monkeypatch, module_name, function_name,
                  lambda *a, **k: (_ for _ in ()).throw(RuntimeError('evidence down')))

    payload = _apply(approved)

    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [
        apply_service.CONTRADICTION_DEPENDENT_EVIDENCE]
    assert payload['abort_detail']['failed_families'] == [family]
    assert payload['rollback_performed'] is True
    assert payload['transaction_committed'] is False
    assert payload['database_writes_performed'] is False
    # Nothing partial survives: no ledger row, no identity, no GameLog, no metadata.
    assert _counts() == before
    assert db.session.query(Ledger).count() == 0
    assert db.session.query(Pitcher).filter(Pitcher.mlb_id == P_DEFERRED).count() == 0
    row = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    assert row.hits_allowed == before_hits
    assert row.stat_correction_count == 0
    assert row.last_stat_correction_source is None
    assert row.last_stat_correction_at is None


@pytest.mark.parametrize('malformed', [
    'not a dict',
    {'evidence_ids': []},
    {'marked_count': 'three', 'evidence_ids': []},
    {'marked_count': -1, 'evidence_ids': []},
    {'marked_count': 1, 'evidence_ids': 'nope'},
    None,
])
def test_a_malformed_marker_result_rolls_back_every_action(approved, monkeypatch,
                                                           malformed):
    before = _counts()
    _break_marker(monkeypatch, 'services.appearance_context_evidence',
                  'mark_game_log_correction_for_appearance_context',
                  lambda *a, **k: malformed)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [
        apply_service.CONTRADICTION_DEPENDENT_EVIDENCE]
    assert _counts() == before
    assert db.session.query(Ledger).count() == 0


def test_an_absent_required_marker_rolls_back_every_action(approved, monkeypatch):
    before = _counts()
    module = __import__('services.inherited_traffic_evidence',
                        fromlist=['mark_game_log_correction_for_inherited_traffic'])
    monkeypatch.delattr(module, 'mark_game_log_correction_for_inherited_traffic')
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [
        apply_service.CONTRADICTION_DEPENDENT_EVIDENCE]
    assert _counts() == before


def test_an_invalidation_result_for_the_wrong_row_rolls_back(approved, monkeypatch):
    # A family that completed for a DIFFERENT row has not invalidated this row's evidence.
    real = sync_service._notify_workload_evidence_game_log_correction

    def _misattributed(game_log, *, sync_run_id=None, strict=False):
        result = real(game_log, sync_run_id=sync_run_id, strict=strict)
        if isinstance(result, dict) and 'game_log_id' in result:
            result = dict(result, game_log_id=(result['game_log_id'] or 0) + 1)
        return result

    monkeypatch.setattr(sync_service, '_notify_workload_evidence_game_log_correction',
                        _misattributed)
    before = _counts()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [
        apply_service.CONTRADICTION_DEPENDENT_EVIDENCE]
    assert _counts() == before


def test_every_updated_row_records_its_three_completed_families(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    records = payload['dependent_evidence_invalidation_results']
    assert len(records) == len(payload['update_results'])
    for record in records:
        assert sorted(record['families']) == sorted(
            sync_service.REQUIRED_EVIDENCE_FAMILIES)
        assert all(item['status'] == 'completed' for item in record['families'].values())
        assert record['all_required_families_completed'] is True
        assert record['failed_families'] == []
        assert record['result_game_log_id'] == record['local_game_log_id']
        assert record['result_sync_run_id'] == payload['governed_operation_id']
    checks = payload['verification_results']
    assert checks['every_updated_row_completed_all_dependent_evidence_families'] is True
    assert checks['every_dependent_evidence_result_belongs_to_its_own_row'] is True
    assert checks[
        'every_dependent_evidence_result_carries_the_governed_operation_id'] is True


# ═══════════════ 22. Exact correction-count delta ═══════════════════════════
def test_every_update_records_an_exact_correction_count_delta_of_one(approved):
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    assert payload['update_results']
    for record in payload['update_results']:
        assert record['prior_stat_correction_count'] == 0
        assert record['resulting_stat_correction_count'] == 1
        assert record['correction_count_delta'] == 1
        stored = db.session.query(GameLog).filter(
            GameLog.id == record['local_game_log_id']).one()
        assert stored.stat_correction_count == (
            record['prior_stat_correction_count'] + 1)
    checks = payload['verification_results']
    assert checks[
        'every_updated_row_incremented_its_correction_count_by_exactly_one'] is True
    assert checks['every_stored_correction_count_is_exactly_one_greater'] is True
    assert checks['every_updated_row_recorded_its_prior_correction_count'] is True


def test_a_nonzero_prior_correction_count_still_requires_a_delta_of_exactly_one(approved):
    row = db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).one()
    row.stat_correction_count = 4
    db.session.add(row)
    db.session.commit()
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_PASS
    record = [r for r in payload['update_results']
              if r['local_game_log_id'] == BR_LOG_ID][0]
    assert record['prior_stat_correction_count'] == 4
    assert record['resulting_stat_correction_count'] == 5
    assert record['correction_count_delta'] == 1
    assert db.session.query(GameLog).filter(
        GameLog.id == BR_LOG_ID).one().stat_correction_count == 5


def test_a_simulated_double_increment_fails_verification_and_rolls_back(approved,
                                                                       monkeypatch):
    real = apply_service._apply_updates
    before = _counts()

    def _double(session, update_actions, **kwargs):
        result = real(session, update_actions, **kwargs)
        for record in result['records']:
            row = session.query(GameLog).filter(
                GameLog.id == record['local_game_log_id']).one()
            row.stat_correction_count = row.stat_correction_count + 1
            session.add(row)
        session.flush()
        return result

    monkeypatch.setattr(apply_service, '_apply_updates', _double)
    payload = _apply(approved)
    assert payload['result'] == apply_service.RESULT_FAIL
    assert payload['decision_reasons'] == [apply_service.CONTRADICTION_VERIFICATION]
    assert 'every_stored_correction_count_is_exactly_one_greater' in payload[
        'abort_detail']['failed_verifications']
    assert _counts() == before
    assert db.session.query(GameLog).filter(
        GameLog.id == BR_LOG_ID).one().stat_correction_count == 0


# ═══════════════ 23. Governed constants are unchanged ═══════════════════════
def test_the_governed_constants_are_unchanged():
    assert (apply_service.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026
            == '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b')
    assert apply_service.CONFIRMATION_PHRASE == 'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06'
    assert apply_service.APPROVED_EXECUTION_CONTRACT['manifest_fingerprint'] == (
        apply_service.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026)
    assert apply_service.APPROVED_EXECUTION_CONTRACT['total_action_count'] == 675
    assert apply_service.EVIDENCE_INVALIDATION_STRICT is True
