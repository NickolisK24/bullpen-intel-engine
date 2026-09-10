"""Matt Festa earned-run correction (2026) — one action, applied once, atomically.

Covers the immutable one-action contract and its refusal of every deviation, the separation
from the closed 675-action repair, the dedicated advisory lock and confirmation phrase, the
full-population and original-repair preconditions, the atomic mutation with strict dependent
evidence invalidation and direct column readback, the reused execution ledger's refusal of a
second execution, the post-commit verification, and the dispatch-only workflow that keeps
every downstream gate blocked.
"""

import ast
import copy
import hashlib
from datetime import date, datetime
from pathlib import Path

import pytest
import re
import sqlalchemy as sa
from flask import Flask

import models.prospect  # noqa: F401
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.official_pitching_line_repair_execution import (
    OfficialPitchingLineRepairExecution as Ledger,
)
from models.pitcher import Pitcher
from services import official_pitching_line_completeness_2026 as completeness
from services import official_pitching_line_matt_festa_apply_2026 as festa
from services import official_pitching_line_repair_apply_2026 as repair_apply
from services import official_pitching_line_repair_closeout_2026 as closeout
from services import official_pitching_line_repair_plan_2026 as planner
from services import season_bullpen_aggregation_2026 as aggregation
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = (REPO_ROOT / 'backend' / 'services'
                / 'official_pitching_line_matt_festa_apply_2026.py')
CLI_PATH = (REPO_ROOT / 'backend' / 'scripts'
            / 'run_official_pitching_line_matt_festa_apply_2026.py')
WORKFLOW_PATH = (REPO_ROOT / '.github' / 'workflows'
                 / 'official_pitching_line_matt_festa_apply.yml')
ORIGINAL_SERVICE_PATH = (REPO_ROOT / 'backend' / 'services'
                         / 'official_pitching_line_repair_apply_2026.py')
ORIGINAL_CLI_PATH = (REPO_ROOT / 'backend' / 'scripts'
                     / 'run_official_pitching_line_repair_apply_2026.py')
ORIGINAL_WORKFLOW_PATH = (REPO_ROOT / '.github' / 'workflows'
                          / 'official_pitching_line_repair_apply.yml')
MIGRATIONS_DIR = REPO_ROOT / 'backend' / 'migrations' / 'versions'
DECISION_RECORD = (REPO_ROOT / 'docs' / 'decisions'
                   / '2026-07-29-matt-festa-earned-run-correction.md')

SEASON = 2026
AS_OF = date(2026, 7, 25)
FESTA_DATE = date(2026, 7, 24)
BR_DATE = date(2026, 7, 20)
SEEDED_AT = datetime(2026, 7, 26, 12, 0, 0)

# The real production identifiers, so the fixture exercises the keys the contract pins.
FESTA_GAME, FESTA_PERSON, FESTA_TEAM, FESTA_OPPONENT = 822952, 670036, 114, 116
FESTA_LOG_ID, FESTA_PITCHER_ROW_ID = 44140, 169
FESTA_HOME_STARTER, FESTA_AWAY_STARTER = 670101, 670102
# The reviewed Brandyn Garcia amendment from the closed 675-action repair.
BR_GAME, BR_PERSON, BR_TEAM, BR_OPPONENT = 825058, 805299, 109, 110
BR_LOG_ID, BR_HOME_STARTER, BR_AWAY_STARTER = 43765, 800001, 800002
# A third game, used to place a defect OUTSIDE the targeted scope.
OTHER_GAME, OTHER_TEAM, OTHER_OPPONENT = 826001, 111, 112
OTHER_HOME_STARTER, OTHER_AWAY_STARTER, OTHER_RELIEVER = 800011, 800012, 800013
# An official person with no local identity at all, used to force an identity action.
UNKNOWN_PERSON = 800021

LEDGER_REVISION = 'c7b3e5a91d48'
# The head the schema actually sits at. The ledger revision is no longer the tip:
# the Foundation 3C game-driven ingestion work-state checkpoint chains onto it,
# purely additively. The fixture seeds THIS so the repair and its post-commit
# completeness check both see the schema production actually has.
GOVERNED_SCHEMA_HEAD = 'b9d4e17c3a80'

TEAM_NAMES = {FESTA_TEAM: 'Cleveland Guardians', FESTA_OPPONENT: 'Team116',
              BR_TEAM: 'Team109', BR_OPPONENT: 'Team110',
              OTHER_TEAM: 'Team111', OTHER_OPPONENT: 'Team112'}
TEAM_ABBR = {FESTA_TEAM: 'CLE', FESTA_OPPONENT: 'T116', BR_TEAM: 'T109',
             BR_OPPONENT: 'T110', OTHER_TEAM: 'T111', OTHER_OPPONENT: 'T112'}
NAMES = {FESTA_PERSON: 'Matt Festa', BR_PERSON: 'Brandyn Garcia'}


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        # The governed ledger revision must be the migration head. A create_all schema has
        # no alembic_version table, so the fixture states the head explicitly rather than
        # letting the precondition pass on an absent value, and drops it again so a
        # persistent test target does not accumulate rows across the session.
        db.session.execute(sa.text('DROP TABLE IF EXISTS alembic_version'))
        db.session.execute(sa.text(
            'CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)'))
        db.session.execute(sa.text(
            'INSERT INTO alembic_version (version_num) VALUES (:v)'),
            {'v': GOVERNED_SCHEMA_HEAD})
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
        'team': {'id': team_id, 'name': TEAM_NAMES[team_id],
                 'abbreviation': TEAM_ABBR[team_id]},
        'pitchers': [mlb_id for mlb_id, _stats in lines],
        'players': {f'ID{mlb_id}': {
            'person': {'id': mlb_id, 'fullName': NAMES.get(mlb_id, f'P{mlb_id}')},
            'stats': {'pitching': stats}} for mlb_id, stats in lines},
    }


def _boxscore(home, away, home_lines, away_lines):
    return {'teams': {'home': _side(home, home_lines), 'away': _side(away, away_lines)}}


def _game(game_pk, home, away, gdate):
    return {'gamePk': game_pk, 'officialDate': gdate.isoformat(), 'gameType': 'R',
            'status': {'statusCode': 'F', 'detailedState': 'Final',
                       'abstractGameState': 'Final'},
            'teams': {'home': {'team': {'id': home, 'name': TEAM_NAMES[home],
                                        'abbreviation': TEAM_ABBR[home]}},
                      'away': {'team': {'id': away, 'name': TEAM_NAMES[away],
                                        'abbreviation': TEAM_ABBR[away]}}}}


def _person(mlb_id):
    return {'id': mlb_id, 'fullName': NAMES.get(mlb_id, f'P{mlb_id}'),
            'primaryPosition': {'abbreviation': 'P', 'code': '1', 'name': 'Pitcher'},
            'pitchHand': {'code': 'R'}}


PEOPLE = {mlb_id: _person(mlb_id) for mlb_id in (
    FESTA_PERSON, FESTA_HOME_STARTER, FESTA_AWAY_STARTER, BR_PERSON, BR_HOME_STARTER,
    BR_AWAY_STARTER, OTHER_HOME_STARTER, OTHER_AWAY_STARTER, OTHER_RELIEVER,
    UNKNOWN_PERSON)}


def _festa_boxscore(*, extra_home_lines=(), festa_line=None):
    home = [_pline(FESTA_HOME_STARTER, gs=1, outs=18, r=2, er=2, h=5, k=6)]
    home.append(festa_line if festa_line is not None else
                _pline(FESTA_PERSON, gs=0, outs=5, r=1, er=1, h=2, bb=0, k=2, hr=0))
    home.extend(extra_home_lines)
    away = [_pline(FESTA_AWAY_STARTER, gs=1, outs=21, r=1, er=1, h=4, k=7)]
    return _boxscore(FESTA_TEAM, FESTA_OPPONENT, home, away)


def _br_boxscore():
    return _boxscore(BR_TEAM, BR_OPPONENT,
                     [_pline(BR_HOME_STARTER, gs=1, outs=18, r=1, er=1, h=4, k=5),
                      _pline(BR_PERSON, gs=0, outs=3, r=0, er=0, h=0, k=1)],
                     [_pline(BR_AWAY_STARTER, gs=1, outs=21, r=2, er=2, h=7, k=8)])


def _other_boxscore(*, reliever_hits=1):
    return _boxscore(OTHER_TEAM, OTHER_OPPONENT,
                     [_pline(OTHER_HOME_STARTER, gs=1, outs=18, r=1, er=1, h=3, k=4),
                      _pline(OTHER_RELIEVER, gs=0, outs=3, r=0, er=0, h=reliever_hits,
                             k=2)],
                     [_pline(OTHER_AWAY_STARTER, gs=1, outs=18, r=2, er=2, h=6, k=5)])


class _FakeMlbClient:
    """Deterministic official evidence. Never reached over the network."""

    def __init__(self, *, festa_box=None, other_reliever_hits=1):
        self.games = [_game(FESTA_GAME, FESTA_TEAM, FESTA_OPPONENT, FESTA_DATE),
                      _game(BR_GAME, BR_TEAM, BR_OPPONENT, BR_DATE),
                      _game(OTHER_GAME, OTHER_TEAM, OTHER_OPPONENT, BR_DATE)]
        self.boxscores = {
            FESTA_GAME: festa_box if festa_box is not None else _festa_boxscore(),
            BR_GAME: _br_boxscore(),
            OTHER_GAME: _other_boxscore(reliever_hits=other_reliever_hits),
        }

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        return [g for g in self.games if start_date <= g['officialDate'] <= end_date]

    def get_game_boxscore(self, game_pk):
        return self.boxscores.get(game_pk)

    def get_player_info(self, player_id):
        return PEOPLE.get(player_id)

    def get_all_teams(self, sport_id=1):
        return [{'id': team, 'name': TEAM_NAMES[team], 'abbreviation': TEAM_ABBR[team]}
                for team in sorted(TEAM_NAMES)]


# ── Local ledger fixtures ─────────────────────────────────────────────────────
def _pitcher(mlb_id, *, row_id=None):
    existing = db.session.query(Pitcher).filter_by(mlb_id=mlb_id).first()
    if existing:
        return existing
    row = Pitcher(mlb_id=mlb_id, full_name=NAMES.get(mlb_id, f'P{mlb_id}'), position='P',
                  active=True)
    if row_id is not None:
        row.id = row_id
    db.session.add(row)
    db.session.commit()
    return row


def _log(mlb_id, *, game_pk, gdate, team, opponent, gs, outs, r=0, er=0, h=0, bb=0, k=0,
         hr=0, log_id=None, pitcher_row_id=None, corrections=None):
    row = _pitcher(mlb_id, row_id=pitcher_row_id)
    log = GameLog(
        pitcher_id=row.id, mlb_game_pk=game_pk, game_date=gdate, game_type='R',
        games_started=gs, innings_pitched_outs=outs, innings_pitched=(outs / 3.0),
        runs_allowed=r, earned_runs=er, hits_allowed=h, walks=bb, strikeouts=k,
        home_runs_allowed=hr, strikes=outs * 2,
        opponent=TEAM_NAMES[opponent], opponent_abbreviation=TEAM_ABBR[opponent],
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_id=team, appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
    )
    if log_id is not None:
        log.id = log_id
    if corrections:
        log.stat_correction_count = corrections['count']
        log.last_stat_correction_source = corrections['source']
        log.last_stat_correction_at = corrections['at']
    db.session.add(log)
    db.session.commit()
    return log


def seed_local(*, festa_earned_runs=0, festa_hits=2, festa_outs=5, other_hits=1,
               skip_festa=False):
    """The local ledger the reviewed one-action manifest was planned against.

    Everything is an exact match except the Cleveland relief line, whose stored earned runs
    are zero against official scoring's one.
    """
    _log(FESTA_HOME_STARTER, game_pk=FESTA_GAME, gdate=FESTA_DATE, team=FESTA_TEAM,
         opponent=FESTA_OPPONENT, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(FESTA_AWAY_STARTER, game_pk=FESTA_GAME, gdate=FESTA_DATE, team=FESTA_OPPONENT,
         opponent=FESTA_TEAM, gs=1, outs=21, r=1, er=1, h=4, k=7)
    if not skip_festa:
        _log(FESTA_PERSON, game_pk=FESTA_GAME, gdate=FESTA_DATE, team=FESTA_TEAM,
             opponent=FESTA_OPPONENT, gs=0, outs=festa_outs, r=1, er=festa_earned_runs,
             h=festa_hits, bb=0, k=2, hr=0, log_id=FESTA_LOG_ID,
             pitcher_row_id=FESTA_PITCHER_ROW_ID)
    else:
        _pitcher(FESTA_PERSON, row_id=FESTA_PITCHER_ROW_ID)
    _log(BR_HOME_STARTER, game_pk=BR_GAME, gdate=BR_DATE, team=BR_TEAM,
         opponent=BR_OPPONENT, gs=1, outs=18, r=1, er=1, h=4, k=5)
    _log(BR_AWAY_STARTER, game_pk=BR_GAME, gdate=BR_DATE, team=BR_OPPONENT,
         opponent=BR_TEAM, gs=1, outs=21, r=2, er=2, h=7, k=8)
    _log(BR_PERSON, game_pk=BR_GAME, gdate=BR_DATE, team=BR_TEAM, opponent=BR_OPPONENT,
         gs=0, outs=3, r=0, er=0, h=0, k=1, log_id=BR_LOG_ID,
         corrections={'count': 1, 'source': repair_apply.CORRECTION_SOURCE,
                      'at': SEEDED_AT})
    _log(OTHER_HOME_STARTER, game_pk=OTHER_GAME, gdate=BR_DATE, team=OTHER_TEAM,
         opponent=OTHER_OPPONENT, gs=1, outs=18, r=1, er=1, h=3, k=4)
    _log(OTHER_AWAY_STARTER, game_pk=OTHER_GAME, gdate=BR_DATE, team=OTHER_OPPONENT,
         opponent=OTHER_TEAM, gs=1, outs=18, r=2, er=2, h=6, k=5)
    _log(OTHER_RELIEVER, game_pk=OTHER_GAME, gdate=BR_DATE, team=OTHER_TEAM,
         opponent=OTHER_OPPONENT, gs=0, outs=3, r=0, er=0, h=other_hits, k=2)


ORIGINAL = festa.IMMUTABLE_CONTRACT['original_repair']


def seed_original_ledger(**overrides):
    """The closed 675-action repair's ledger row, exactly as it committed."""
    values = {
        'capability': 'official_pitching_line_repair_apply_2026_v1',
        'approved_manifest_fingerprint': ORIGINAL['approved_manifest_fingerprint'],
        'regenerated_manifest_fingerprint': ORIGINAL['approved_manifest_fingerprint'],
        'planner_git_sha': '0' * 40, 'apply_git_sha': '0' * 40,
        'season': 2026, 'as_of_date': AS_OF, 'accepted_baseline_version': 'v2',
        'amendment_id': repair_apply.APPROVED_EXECUTION_CONTRACT['amendment_id'],
        'status': Ledger.STATUS_COMPLETED,
        'identity_action_count': 70, 'insert_action_count': 445,
        'update_action_count': 160, 'total_action_count': 675,
        'started_at': SEEDED_AT, 'completed_at': SEEDED_AT, 'committed_at': SEEDED_AT,
    }
    values.update(overrides)
    row = Ledger(**values)
    db.session.add(row)
    db.session.commit()
    return row


# ── Dependent-evidence fixtures ───────────────────────────────────────────────
FAMILY_RULE_ID = {
    family: sync_service.direct_game_log_evidence_registry()[family]['rule_ids'][0]
    for family in sync_service.REQUIRED_EVIDENCE_FAMILIES
}


def seed_dependent_evidence(*, source_pk, family, objects=1, citations_per_object=1):
    rule_id = FAMILY_RULE_ID[family]
    created = []
    for index in range(objects):
        evidence = EvidenceObject(
            evidence_key=f'{rule_id}:{source_pk}:{index}', evidence_type='metric',
            subject_type='pitcher', subject_id='1', subject_key=f'pitcher:1:{index}',
            product_date=FESTA_DATE, claim_template_id=f'{rule_id}.v1',
            rendered_claim='fixture', rule_id=rule_id, rule_version=1,
            rule_definition_hash='0' * 64, typed_cited_inputs=[], computation_trace={},
            completeness_state=EvidenceObject.COMPLETENESS_COMPLETE,
            posture=EvidenceObject.POSTURE_INTERNAL_ONLY, source='fixture',
            recompute_status=EvidenceObject.RECOMPUTE_CURRENT)
        db.session.add(evidence)
        db.session.flush()
        for order in range(citations_per_object):
            db.session.add(EvidenceCitation(
                evidence_object_id=evidence.id, source_family='game_logs',
                source_table='game_logs', source_pk=str(source_pk),
                source_field_names=['earned_runs'], citation_role='supporting_input',
                cited_values={'order': order}, provenance={'fixture': True}))
        created.append(evidence.id)
    db.session.commit()
    return created


def _current_count(source_pk, family=None):
    from services import evidence_contract
    rule_ids = None if family is None else (FAMILY_RULE_ID[family],)
    return len(evidence_contract.current_dependent_evidence_ids(
        source_table='game_logs', source_pk=source_pk, rule_ids=rule_ids,
        session=db.session))


# ── Plan, diagnostic, and the fixture-scale approved contract ────────────────
def _plan(client):
    return planner.run_repair_plan(
        season=SEASON, as_of_date=AS_OF, preview_limit=100, team_id=FESTA_TEAM,
        game_pk=FESTA_GAME, client=client, session=db.session)


def _diagnostic(client):
    return completeness.run_diagnostic(
        season=SEASON, as_of_date=AS_OF, detail_limit=100, client=client,
        session=db.session)


def _clean_aggregation(**kwargs):
    """A complete, passing aggregation payload for whichever mode is requested."""
    official = kwargs['include_official_validation']
    return {
        'result': 'pass', 'exit_code': 0,
        'mode': 'official_validation' if official else 'local_only',
        'local_aggregation': {'teams_complete': 30, 'teams_partial': 0,
                              'teams_unavailable': 0},
        'official_validation': {
            'teams_matched': 30, 'teams_mismatched': 0,
            'mandatory_metric_mismatches': 0, 'unavailable_evidence_count': 0,
            'official_games_missing_unique_starter': 0,
            'official_games_with_multiple_starters': 0},
        'reconciliations': {
            'canonical_outs_match': True, 'team_totals_reconcile': True,
            'league_totals_reconcile': True, 'bullpen_outs_reconcile': True,
            'all_mandatory_metrics_match': bool(official),
            'canonical_game_grain_bullpen_outs': 12},
    }


def _fixture_contract(plan, diagnostic):
    """The approved contract for this fixture, derived from its own plan and population.

    Every governed value is pinned exactly as the production contract pins its own — the
    fingerprints and population sizes differ, the shape and the strictness do not.
    """
    action = (plan.get('repair_manifest') or [{}])[0]
    contract = copy.deepcopy(festa.IMMUTABLE_CONTRACT)
    contract['approved_manifest_fingerprint'] = plan['repair_manifest_fingerprint']
    # The approved plan-generation SHA is deliberately NOT taken from the fresh plan: the
    # whole point is that the runtime SHA may differ from the reviewed one. The fixture
    # keeps the real pinned value, and the fresh planner reports whatever it reports.
    contract['approved_planner_source_sha256'] = festa.planner_source_sha256()
    contract['action']['comparison_fingerprint'] = action.get('comparison_fingerprint')
    contract['action']['source_fingerprint'] = action.get('source_fingerprint')
    contract['expected_population'] = {
        name: diagnostic.get(name) for name in contract['expected_population']}
    contract['verified_population'] = dict(
        contract['verified_population'],
        official_pitching_lines=diagnostic['official_pitching_lines'],
        local_pitching_lines=diagnostic['local_pitching_lines'],
        exact_match_count=diagnostic['official_pitching_lines'])
    return contract


@pytest.fixture
def approved(monkeypatch, app):
    """Seed the reviewed state, then pin the resulting plan as the approved contract."""
    seed_local()
    seed_original_ledger()
    client = _FakeMlbClient()
    plan = _plan(client)
    diagnostic = _diagnostic(client)
    contract = _fixture_contract(plan, diagnostic)
    monkeypatch.setattr(festa, 'IMMUTABLE_CONTRACT', contract)
    monkeypatch.setattr(festa, 'APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026',
                        contract['approved_manifest_fingerprint'])
    monkeypatch.setattr(aggregation, 'run_aggregation', _clean_aggregation)
    return type('Approved', (), {'client': client, 'plan': plan, 'contract': contract,
                                 'diagnostic': diagnostic})


def _apply(approved, *, client=None):
    return festa.apply_matt_festa_earned_run_correction(
        generated_at='2026-07-29T00:00:00Z', apply_git_sha='f' * 40,
        client=client or approved.client, session=db.session)


def _stored(log_id=FESTA_LOG_ID):
    db.session.expire_all()
    return db.session.query(GameLog).filter(GameLog.id == log_id).one()


def _festa_ledger_rows(contract):
    return (db.session.query(Ledger)
            .filter(Ledger.approved_manifest_fingerprint
                    == contract['approved_manifest_fingerprint'])
            .all())


# ══ 1-6. The pinned contract and its separation from the closed repair ═══════
def test_1_the_exact_approved_targeted_fingerprint_is_pinned():
    assert festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 == (
        '903766c4d71652d102410d924d1adf2479f21b07a6742e2ce407385a06ac8f2b')
    assert festa.IMMUTABLE_CONTRACT['approved_manifest_fingerprint'] == (
        '903766c4d71652d102410d924d1adf2479f21b07a6742e2ce407385a06ac8f2b')
    assert festa.CAPABILITY == 'official_pitching_line_matt_festa_apply_2026_v1'


def test_2_the_original_approved_fingerprint_remains_unchanged():
    assert repair_apply.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026 \
        == '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b'
    assert ORIGINAL['approved_manifest_fingerprint'] == (
        '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b')
    assert ORIGINAL['identity_action_count'] == 70
    assert ORIGINAL['insert_action_count'] == 445
    assert ORIGINAL['update_action_count'] == 160
    assert ORIGINAL['total_action_count'] == 675


def test_3_the_original_confirmation_phrase_remains_unchanged():
    assert repair_apply.CONFIRMATION_PHRASE == (
        'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06')
    assert (repair_apply.CONFIRMATION_PHRASE
            in ORIGINAL_CLI_PATH.read_text(encoding='utf-8'))
    assert (repair_apply.CONFIRMATION_PHRASE
            in ORIGINAL_WORKFLOW_PATH.read_text(encoding='utf-8'))


def test_4_the_new_confirmation_phrase_is_distinct_and_unusable_elsewhere():
    assert festa.CONFIRMATION_PHRASE == 'APPLY-2026-MATT-FESTA-ER-903766C4'
    assert festa.CONFIRMATION_PHRASE != repair_apply.CONFIRMATION_PHRASE
    # Neither phrase can be pasted into the other's command or workflow.
    assert festa.CONFIRMATION_PHRASE not in ORIGINAL_CLI_PATH.read_text(encoding='utf-8')
    assert festa.CONFIRMATION_PHRASE not in ORIGINAL_WORKFLOW_PATH.read_text(
        encoding='utf-8')
    assert repair_apply.CONFIRMATION_PHRASE not in CLI_PATH.read_text(encoding='utf-8')
    assert repair_apply.CONFIRMATION_PHRASE not in WORKFLOW_PATH.read_text(
        encoding='utf-8')
    # The CLI's literal copy, checked before any import, agrees with the service.
    cli = ast.parse(CLI_PATH.read_text(encoding='utf-8'))
    literals = {node.targets[0].id: node.value.value for node in cli.body
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
                and isinstance(node.targets[0], ast.Name)}
    assert literals['CONFIRMATION_PHRASE'] == festa.CONFIRMATION_PHRASE
    assert literals['CAPABILITY'] == festa.CAPABILITY


def test_5_the_exact_target_scope_is_immutable():
    contract = festa.IMMUTABLE_CONTRACT
    assert contract['season'] == 2026
    assert contract['as_of_date'] == '2026-07-25'
    assert contract['team_id'] == 114
    assert contract['game_pk'] == 822952
    assert contract['planner_capability'] == planner.CAPABILITY
    assert contract['approved_planner_git_sha'] == (
        'c4a0b3e4e33d64c5cecea3151ff3c30df7e0c5fa')
    assert contract['migration_head'] == GOVERNED_SCHEMA_HEAD
    assert contract['amendment_id'] == 'post_repair_matt_festa_earned_runs_2026'
    action = contract['action']
    assert action['action_id'] == 'gamelog:update:44140:822952:670036'
    assert action['stable_key'] == '822952:670036:114'
    assert action['local_game_log_id'] == 44140
    assert action['local_pitcher_id'] == 169
    assert action['official_mlb_person_id'] == 670036
    assert action['appearance_team_id'] == 114
    assert action['changed_fields'] == ['earned_runs']
    assert action['current_values'] == {'earned_runs': 0}
    assert action['proposed_values'] == {'earned_runs': 1}
    assert festa.APPROVED_MUTABLE_FIELD == 'earned_runs'
    assert festa.APPROVED_VALUE_BEFORE == 0
    assert festa.APPROVED_VALUE_AFTER == 1
    # The entrypoint accepts no governed input at all: only wiring parameters.
    import inspect
    parameters = set(
        inspect.signature(festa.apply_matt_festa_earned_run_correction).parameters)
    assert parameters == {'generated_at', 'apply_git_sha', 'client', 'session'}


def test_6_generic_subset_plans_remain_not_apply_eligible(approved):
    plan = approved.plan
    assert plan['plan_scope'] == planner.PLAN_SCOPE_SUBSET == 'diagnostic_subset'
    assert plan['plan_status'] == planner.PLAN_BLOCKED_SUBSET
    assert plan['plan_status'] == 'diagnostic_subset_not_apply_eligible'
    assert plan['repair_apply_gate'] == planner.GATE_BLOCKED_SUBSET
    assert plan['repair_apply_gate'] == 'blocked_subset_not_apply_eligible'
    assert plan['result'] == planner.RESULT_INCONCLUSIVE
    assert plan['database_writes_performed'] is False


# ══ 7-8. What the dedicated apply accepts ════════════════════════════════════
def test_7_only_the_expected_subset_status_and_baseline_drift_reason_are_accepted(
        approved):
    verification = festa.verify_regenerated_plan(approved.plan)
    assert verification['failed'] == []
    assert verification['checks'][
        'plan_status_is_not_apply_eligible'] is True
    assert verification['checks'][
        'decision_reasons_are_exactly_the_reviewed_reasons'] is True
    assert approved.plan['decision_reasons'] == [planner.BLOCK_BASELINE_DRIFT]
    assert planner.BLOCK_BASELINE_DRIFT == 'accepted_baseline_drift'
    # A different status or reason is refused.
    for mutated in ({'plan_status': planner.PLAN_READY},
                    {'decision_reasons': ['something_else']},
                    {'result': planner.RESULT_PASS},
                    {'plan_scope': planner.PLAN_SCOPE_FULL}):
        assert festa.verify_regenerated_plan(dict(approved.plan, **mutated))['failed']


def test_8_the_exact_one_action_manifest_passes(approved):
    verification = festa.verify_regenerated_plan(approved.plan)
    assert verification['failed'] == []
    assert verification['failed_action_fields'] == []
    assert all(verification['checks'].values())
    assert all(verification['action_checks'].values())
    assert approved.plan['repair_manifest_action_count'] == 1
    assert approved.plan['actions_by_type'] == {
        planner.ACTION_IDENTITY_CREATE: 0, planner.ACTION_GAME_LOG_INSERT: 0,
        planner.ACTION_GAME_LOG_UPDATE: 1}


# ══ 9-18. Every deviation refuses before the first write ═════════════════════
def _assert_refused_without_writes(payload, *, reason=None):
    assert payload['transaction_committed'] is False
    assert payload['database_writes_performed'] is False
    assert payload['execution_ledger_id'] is None
    assert payload['result'] in (festa.RESULT_INCONCLUSIVE, festa.RESULT_FAIL)
    assert payload['exit_code'] != 0
    assert payload['unresolved_issues']
    for gate in festa.DOWNSTREAM_GATES:
        assert payload[gate] == festa.GATE_BLOCKED
    if reason is not None:
        assert payload['decision_reasons'] == [reason]


def test_9_the_pre_fix_two_field_fingerprint_is_refused(approved):
    # The manifest the planner produced before the derived-innings correction was removed.
    assert festa.REFUSED_PRE_FIX_MANIFEST_FINGERPRINT_2026 == (
        '257ff3a64261d69908248de81e6c67a83d1e0357241cacab897fe610f91cb838')
    assert (festa.REFUSED_PRE_FIX_MANIFEST_FINGERPRINT_2026
            != festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026)
    plan = dict(approved.plan,
                repair_manifest_fingerprint=festa
                .REFUSED_PRE_FIX_MANIFEST_FINGERPRINT_2026)
    verification = festa.verify_regenerated_plan(plan)
    assert 'regenerated_fingerprint_equals_the_approved_fingerprint' in \
        verification['failed']
    # And a two-field manifest never matches the reviewed action either.
    two_field = copy.deepcopy(approved.plan)
    two_field['repair_manifest'][0]['changed_fields'] = ['earned_runs',
                                                         'innings_pitched']
    two_field['repair_manifest'][0]['proposed_values'] = {
        'earned_runs': 1, 'innings_pitched': 5 / 3.0}
    assert 'regenerated_action_matches_the_reviewed_contract' in \
        festa.verify_regenerated_plan(two_field)['failed']


def test_10_any_regenerated_fingerprint_mismatch_refuses_before_writes(
        approved, monkeypatch):
    monkeypatch.setattr(
        festa, 'IMMUTABLE_CONTRACT',
        dict(approved.contract,
             approved_manifest_fingerprint='0' * 63 + '1'))
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_FINGERPRINT_MISMATCH)
    assert _stored().earned_runs == 0
    assert _festa_ledger_rows(approved.contract) == []


def test_11_a_missing_action_refuses(approved, monkeypatch):
    # The stored row already agrees with official scoring: the plan has zero actions.
    db.session.query(GameLog).filter(GameLog.id == FESTA_LOG_ID).update(
        {'earned_runs': 1}, synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    assert payload['planner_verification']['checks'][
        'exactly_one_action_planned'] is False
    _assert_refused_without_writes(payload)
    assert _festa_ledger_rows(approved.contract) == []


def test_12_an_extra_action_refuses(approved):
    # A second defect inside the SAME targeted scope produces a second update action.
    db.session.query(GameLog).filter(GameLog.id != FESTA_LOG_ID).filter(
        GameLog.mlb_game_pk == FESTA_GAME).update(
        {'hits_allowed': 99}, synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    assert payload['planner_verification']['checks'][
        'exactly_one_action_planned'] is False
    _assert_refused_without_writes(payload)


def test_13_an_identity_action_refuses(approved):
    # Official evidence for a person with no local identity at all, inside the scope.
    client = _FakeMlbClient(festa_box=_festa_boxscore(
        extra_home_lines=[_pline(UNKNOWN_PERSON, gs=0, outs=3, r=0, er=0, h=1, k=1)]))
    payload = _apply(approved, client=client)
    checks = payload['planner_verification']['checks']
    assert checks['zero_identity_actions'] is False
    _assert_refused_without_writes(payload)


def test_14_an_insertion_action_refuses(approved):
    # An official line with an existing local identity but no local GameLog row.
    _pitcher(UNKNOWN_PERSON)
    client = _FakeMlbClient(festa_box=_festa_boxscore(
        extra_home_lines=[_pline(UNKNOWN_PERSON, gs=0, outs=3, r=0, er=0, h=1, k=1)]))
    payload = _apply(approved, client=client)
    checks = payload['planner_verification']['checks']
    assert checks['zero_insertion_actions'] is False
    _assert_refused_without_writes(payload)


def test_15_any_changed_field_other_than_earned_runs_refuses(approved):
    db.session.query(GameLog).filter(GameLog.id == FESTA_LOG_ID).update(
        {'hits_allowed': 7}, synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    assert payload['planner_verification']['action_checks']['changed_fields'] is False
    _assert_refused_without_writes(payload)
    assert _stored().earned_runs == 0


def test_16_any_value_other_than_zero_to_one_refuses(approved):
    # Official earned runs of three against a stored two is still an earned-run mismatch,
    # and still exactly one action — but it is not the reviewed 0 -> 1.
    db.session.query(GameLog).filter(GameLog.id == FESTA_LOG_ID).update(
        {'earned_runs': 2}, synchronize_session=False)
    db.session.commit()
    client = _FakeMlbClient(festa_box=_festa_boxscore(
        festa_line=_pline(FESTA_PERSON, gs=0, outs=5, r=1, er=3, h=2, bb=0, k=2, hr=0)))
    payload = _apply(approved, client=client)
    action_checks = payload['planner_verification']['action_checks']
    assert action_checks['current_values'] is False
    assert action_checks['proposed_values'] is False
    _assert_refused_without_writes(payload)
    assert _stored().earned_runs == 2


def test_17_any_source_fingerprint_mismatch_refuses(approved, monkeypatch):
    contract = copy.deepcopy(approved.contract)
    contract['action']['source_fingerprint'] = 'a' * 64
    monkeypatch.setattr(festa, 'IMMUTABLE_CONTRACT', contract)
    payload = _apply(approved)
    assert payload['planner_verification']['failed_action_fields'] == [
        'source_fingerprint']
    _assert_refused_without_writes(payload, reason=festa.ABORT_ACTION_CONTRACT)


def test_18_any_comparison_fingerprint_mismatch_refuses(approved, monkeypatch):
    contract = copy.deepcopy(approved.contract)
    contract['action']['comparison_fingerprint'] = 'b' * 64
    monkeypatch.setattr(festa, 'IMMUTABLE_CONTRACT', contract)
    payload = _apply(approved)
    assert payload['planner_verification']['failed_action_fields'] == [
        'comparison_fingerprint']
    _assert_refused_without_writes(payload, reason=festa.ABORT_ACTION_CONTRACT)


# ══ 19-23. Identity, population, and the untouched original repair ═══════════
@pytest.mark.parametrize('field,value', [
    ('official_mlb_person_id', 999999),
    ('mlb_game_pk', 999999),
    ('appearance_team_id', 999),
    ('official_role', 'starter'),
    ('local_pitcher_id', 99999),
    ('local_game_log_id', 99999),
    ('official_name', 'Somebody Else'),
    ('official_team_name', 'Some Other Club'),
    ('stable_key', '1:2:3'),
    ('game_date', '2020-01-01'),
])
def test_19_any_target_identity_game_team_role_or_row_mismatch_refuses(
        approved, monkeypatch, field, value):
    contract = copy.deepcopy(approved.contract)
    contract['action'][field] = value
    monkeypatch.setattr(festa, 'IMMUTABLE_CONTRACT', contract)
    payload = _apply(approved)
    assert payload['planner_verification']['failed_action_fields']
    _assert_refused_without_writes(payload)
    assert _stored().earned_runs == 0


def test_19b_a_stored_row_that_is_not_the_reviewed_state_refuses_under_the_lock(
        approved, monkeypatch):
    # The plan and the population still agree; only the pinned row state disagrees.
    monkeypatch.setattr(festa, 'TARGET_ROW_BEFORE',
                        dict(festa.TARGET_ROW_BEFORE, strikeouts=99))
    payload = _apply(approved)
    assert payload['target_row_precondition']['failed'] == ['target_strikeouts_matches']
    _assert_refused_without_writes(payload, reason=festa.ABORT_TARGET_ROW)
    assert payload['rollback_performed'] is True
    assert _stored().earned_runs == 0


def test_19c_a_target_row_whose_official_identity_disagrees_refuses(
        approved, monkeypatch):
    monkeypatch.setattr(festa, 'TARGET_OFFICIAL_PERSON_ID', 999999)
    payload = _apply(approved)
    assert 'target_official_person_matches' in payload['target_row_precondition'][
        'failed']
    _assert_refused_without_writes(payload, reason=festa.ABORT_TARGET_ROW)


def test_20_any_additional_full_population_defect_refuses(approved):
    # A defect OUTSIDE the targeted scope: the one-action plan is unchanged, but the
    # season is no longer a single-defect population.
    db.session.query(GameLog).filter(
        GameLog.mlb_game_pk == OTHER_GAME,
        GameLog.games_started == 0).update({'hits_allowed': 9},
                                           synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    assert payload['planner_verification']['failed'] == []
    assert payload['population_precondition']['failed']
    _assert_refused_without_writes(payload, reason=festa.ABORT_POPULATION)
    assert _stored().earned_runs == 0
    assert _festa_ledger_rows(approved.contract) == []


def test_21_a_missing_original_ledger_record_refuses(approved):
    db.session.query(Ledger).filter(
        Ledger.approved_manifest_fingerprint
        == ORIGINAL['approved_manifest_fingerprint']).delete(synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    assert 'exactly_one_original_ledger_row' in payload[
        'original_repair_precondition']['failed']
    _assert_refused_without_writes(payload, reason=festa.ABORT_ORIGINAL_REPAIR)
    assert payload['result'] == festa.RESULT_FAIL


@pytest.mark.parametrize('overrides,failing', [
    ({'identity_action_count': 69, 'total_action_count': 674},
     'original_identity_count_matches'),
    ({'insert_action_count': 444, 'total_action_count': 674},
     'original_insert_count_matches'),
    ({'update_action_count': 159, 'total_action_count': 674},
     'original_update_count_matches'),
    ({'season': 2025}, 'original_season_matches'),
    ({'as_of_date': date(2026, 7, 24)}, 'original_as_of_date_matches'),
])
def test_22_a_contradictory_original_ledger_record_refuses(approved, overrides, failing):
    row = (db.session.query(Ledger)
           .filter(Ledger.approved_manifest_fingerprint
                   == ORIGINAL['approved_manifest_fingerprint']).one())
    for name, value in overrides.items():
        setattr(row, name, value)
    db.session.commit()
    payload = _apply(approved)
    assert failing in payload['original_repair_precondition']['failed']
    _assert_refused_without_writes(payload, reason=festa.ABORT_ORIGINAL_REPAIR)


@pytest.mark.parametrize('overrides', [
    {'stat_correction_count': 2},
    {'last_stat_correction_source': 'something_else'},
])
def test_23_an_incorrect_brandyn_garcia_state_refuses(approved, overrides):
    db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).update(
        overrides, synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    assert 'reviewed_amendment_state_is_intact' in payload[
        'original_repair_precondition']['failed']
    _assert_refused_without_writes(payload, reason=festa.ABORT_ORIGINAL_REPAIR)
    assert _stored().earned_runs == 0


def test_23b_a_reverted_brandyn_garcia_stat_refuses_at_the_population_gate(approved):
    # Restoring the pre-repair hits value contradicts official evidence, so the season is
    # no longer a single-defect population and the run refuses one gate earlier.
    db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).update(
        {'hits_allowed': 1}, synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    assert payload['population_precondition']['failed']
    _assert_refused_without_writes(payload, reason=festa.ABORT_POPULATION)
    assert _stored().earned_runs == 0
    assert _stored(BR_LOG_ID).hits_allowed == 1


def test_23c_a_missing_brandyn_garcia_row_refuses(approved):
    db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).delete(
        synchronize_session=False)
    db.session.commit()
    payload = _apply(approved)
    # A deleted row is a missing official line, so the population gate refuses first;
    # either way nothing is written.
    _assert_refused_without_writes(payload)
    assert _stored().earned_runs == 0


def test_24_an_existing_completed_target_fingerprint_refuses_without_writes(approved):
    seed_original_ledger(
        capability=festa.CAPABILITY,
        approved_manifest_fingerprint=approved.contract['approved_manifest_fingerprint'],
        regenerated_manifest_fingerprint=approved.contract[
            'approved_manifest_fingerprint'],
        amendment_id=approved.contract['amendment_id'],
        identity_action_count=0, insert_action_count=0, update_action_count=1,
        total_action_count=1)
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_ALREADY_COMPLETED)
    assert payload['abort_detail']['execution_ledger_id']
    assert payload['rollback_performed'] is True
    assert _stored().earned_runs == 0
    assert len(_festa_ledger_rows(approved.contract)) == 1


# ══ 25. The dedicated advisory lock ══════════════════════════════════════════
def test_25_a_dedicated_advisory_lock_is_used(approved):
    assert festa.ADVISORY_LOCK_CONTRACT == (
        'official_pitching_line_matt_festa_2026.transaction_advisory_lock')
    assert festa.ADVISORY_LOCK_CONTRACT != repair_apply.ADVISORY_LOCK_CONTRACT
    assert festa.ADVISORY_LOCK_KEY != repair_apply.ADVISORY_LOCK_KEY
    payload = _apply(approved)
    lock = payload['advisory_lock']
    assert lock['contract'] == festa.ADVISORY_LOCK_CONTRACT
    assert lock['key'] == festa.ADVISORY_LOCK_KEY
    if db.session.get_bind().dialect.name == 'postgresql':
        assert lock['status'] == festa.LOCK_ACQUIRED
        assert lock['acquired'] is True
    else:
        assert lock['status'] == festa.LOCK_SINGLE_WRITER_DIALECT


def test_25b_an_unavailable_lock_refuses_without_writes(approved, monkeypatch):
    monkeypatch.setattr(festa, 'acquire_targeted_advisory_lock',
                        lambda session: {'contract': festa.ADVISORY_LOCK_CONTRACT,
                                         'key': festa.ADVISORY_LOCK_KEY,
                                         'dialect': 'postgresql',
                                         'status': festa.LOCK_UNAVAILABLE,
                                         'acquired': False})
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_LOCK_UNAVAILABLE)
    assert _stored().earned_runs == 0


# ══ 26-32. What the transaction actually changed ═════════════════════════════
def test_26_only_game_log_44140_is_mutated(approved):
    before = {row.id: (row.earned_runs, row.hits_allowed, row.stat_correction_count)
              for row in db.session.query(GameLog).all()}
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    watch = payload['mutation_watch']
    assert watch['mutated_game_log_ids'] == [FESTA_LOG_ID]
    assert watch['mutated_game_log_count'] == 1
    db.session.expire_all()
    after = {row.id: (row.earned_runs, row.hits_allowed, row.stat_correction_count)
             for row in db.session.query(GameLog).all()}
    assert set(before) == set(after)
    for log_id in before:
        if log_id != FESTA_LOG_ID:
            assert before[log_id] == after[log_id], log_id


def test_27_only_earned_runs_plus_correction_metadata_changes(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    watch = payload['mutation_watch']
    assert watch['mutated_game_log_stat_fields'] == ['earned_runs']
    assert set(watch['mutated_game_log_metadata_fields']) <= set(
        festa.CORRECTION_METADATA_FIELDS)
    assert set(watch['mutated_game_log_fields']) == (
        {'earned_runs'} | set(watch['mutated_game_log_metadata_fields']))
    assert _stored().earned_runs == 1
    assert payload['verification_results']['earned_runs_is_exactly_one'] is True
    assert payload['verification_results'][
        'changed_baseball_stat_fields_are_exactly_the_approved_field'] is True


def test_28_innings_pitched_remains_unchanged(approved):
    before = _stored().innings_pitched
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert _stored().innings_pitched == before
    assert payload['verification_results']['innings_pitched_is_unchanged'] is True
    assert payload['verification_results']['no_float_field_was_written'] is True
    assert 'innings_pitched' not in payload['mutation_watch']['mutated_game_log_fields']


def test_29_innings_pitched_outs_remains_unchanged(approved):
    before = _stored().innings_pitched_outs
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert _stored().innings_pitched_outs == before == 5
    assert payload['verification_results']['innings_pitched_outs_is_unchanged'] is True


def test_30_all_other_mandatory_stats_remain_unchanged(approved):
    fields = ('games_started', 'runs_allowed', 'hits_allowed', 'walks', 'strikeouts',
              'home_runs_allowed', 'pitcher_id', 'mlb_game_pk', 'game_date',
              'appearance_team_id', 'appearance_team_source', 'appearance_team_status',
              'appearance_team_reason', 'opponent', 'opponent_abbreviation')
    row = _stored()
    before = {name: getattr(row, name) for name in fields}
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    row = _stored()
    assert {name: getattr(row, name) for name in fields} == before
    for name in fields:
        assert payload['verification_results'][f'{name}_is_unchanged'] is True
    assert payload['verification_results']['every_untouched_field_is_unchanged'] is True


def test_31_the_correction_count_increases_exactly_once(approved):
    before = int(_stored().stat_correction_count or 0)
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert int(_stored().stat_correction_count) == before + 1
    assert payload['verification_results'][
        'correction_count_delta_is_exactly_one'] is True
    assert payload['correction_metadata_before']['stat_correction_count'] == before
    assert payload['correction_metadata_after']['stat_correction_count'] == before + 1


def test_32_correction_source_timestamp_and_operation_id_are_populated(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    row = _stored()
    assert row.last_stat_correction_source == repair_apply.CORRECTION_SOURCE
    assert row.last_stat_correction_source == 'official_pitching_line_repair'
    assert row.last_stat_correction_at is not None
    operation_id = festa.governed_operation_id()
    assert row.last_stat_correction_sync_run_id == operation_id
    # Deterministic, derived from THIS approved fingerprint, and not the original repair's.
    assert operation_id == festa.governed_operation_id()
    assert 0 < operation_id <= 0x7FFFFFFF
    assert payload['governed_operation_id'] == operation_id
    for name in ('correction_source_is_the_governed_source',
                 'correction_timestamp_is_populated',
                 'governed_operation_id_is_stamped'):
        assert payload['verification_results'][name] is True


# ══ 33-35. Dependent evidence ════════════════════════════════════════════════
def test_33_all_evidence_families_complete_in_strict_mode(approved):
    for family in sync_service.REQUIRED_EVIDENCE_FAMILIES:
        seed_dependent_evidence(source_pk=FESTA_LOG_ID, family=family, objects=2)
    assert _current_count(FESTA_LOG_ID) == 2 * len(
        sync_service.REQUIRED_EVIDENCE_FAMILIES)
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert festa.EVIDENCE_INVALIDATION_STRICT is True
    invalidation = payload['dependent_evidence_invalidation']
    assert invalidation['failed'] == []
    assert invalidation['failed_families'] == []
    assert invalidation['rows_invalidated'] == 1
    assert sorted(invalidation['families']) == sorted(
        sync_service.REQUIRED_EVIDENCE_FAMILIES)
    for family in invalidation['families'].values():
        assert family['status'] == festa.EVIDENCE_FAMILY_COMPLETED
        assert family['exhaustive'] is True
        assert family['remaining_current_dependency_count'] == 0
    assert invalidation['final_unscoped_current_dependency_count'] == 0
    assert invalidation['final_unscoped_residual_rule_ids'] == []
    assert _current_count(FESTA_LOG_ID) == 0


def test_34_an_evidence_family_failure_rolls_back(approved, monkeypatch):
    def _raise(game_log, **kwargs):  # noqa: ARG001
        raise sync_service.WorkloadEvidenceInvalidationError(
            'fixture', failed_families=['workload'], families={})

    monkeypatch.setattr(sync_service,
                        '_notify_workload_evidence_game_log_correction', _raise)
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_DEPENDENT_EVIDENCE)
    assert payload['result'] == festa.RESULT_FAIL
    assert payload['rollback_performed'] is True
    assert _stored().earned_runs == 0
    assert _festa_ledger_rows(approved.contract) == []


def test_35_a_residual_dependency_failure_rolls_back(approved, monkeypatch):
    real = sync_service._notify_workload_evidence_game_log_correction

    def _residual(game_log, **kwargs):
        result = dict(real(game_log, **kwargs))
        result['final_unscoped_current_dependency_count'] = 3
        result['final_unscoped_residual_rule_ids'] = ['some.unregistered.rule']
        result['all_direct_game_log_dependencies_exhausted'] = False
        return result

    monkeypatch.setattr(sync_service,
                        '_notify_workload_evidence_game_log_correction', _residual)
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_DEPENDENT_EVIDENCE)
    assert 'no_unregistered_residual_dependency_remains' in payload[
        'dependent_evidence_invalidation']['failed']
    assert 'final_unscoped_dependency_count_is_zero' in payload[
        'dependent_evidence_invalidation']['failed']
    assert _stored().earned_runs == 0
    assert _festa_ledger_rows(approved.contract) == []


# ══ 36-38. Readback and the mutation watch ═══════════════════════════════════
def test_36_a_direct_column_readback_is_used(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    readback = payload['direct_readback']
    assert readback['row_present'] is True
    assert readback['stored']['earned_runs'] == 1
    assert readback['stored']['id'] == FESTA_LOG_ID
    assert readback['correction_metadata']['last_stat_correction_source'] == (
        repair_apply.CORRECTION_SOURCE)
    # The readback is an explicit narrow SELECT, not an ORM object read: the identity map
    # cannot answer for the database.
    source = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    readback_fn = next(node for node in ast.walk(source)
                       if isinstance(node, ast.FunctionDef)
                       and node.name == '_direct_readback')
    calls = {ast.unparse(node.func) for node in ast.walk(readback_fn)
             if isinstance(node, ast.Call)}
    assert 'sa.select' in calls
    assert not any(call.endswith('.query') for call in calls)


def test_37_zero_deletes_occur(approved):
    before = db.session.query(GameLog).count()
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert payload['mutation_watch']['deleted_object_count'] == 0
    assert payload['mutation_watch']['deleted_object_types'] == []
    assert payload['verification_results']['no_delete_occurred'] is True
    assert db.session.query(GameLog).count() == before


def test_37b_no_delete_operation_exists_in_the_service_script_or_workflow():
    for path in (SERVICE_PATH, CLI_PATH):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        attributes = {node.attr for node in ast.walk(tree)
                      if isinstance(node, ast.Attribute)}
        assert 'delete' not in attributes, path
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in ('delete', 'drop', 'truncate'), path
            if isinstance(node, ast.Call) and ast.unparse(node.func) == 'sa.text':
                statement = ' '.join(ast.unparse(arg) for arg in node.args).lower()
                for forbidden in ('delete', 'drop', 'truncate'):
                    assert forbidden not in statement, statement
    shell = _workflow_shell().lower()
    for forbidden in ('delete from', 'drop table', 'truncate table', 'rm -', 'unlink('):
        assert forbidden not in shell, forbidden


def test_38_zero_existing_pitcher_mutations_occur(approved):
    before = {row.id: (row.full_name, row.team_id, row.active, row.position)
              for row in db.session.query(Pitcher).all()}
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert payload['mutation_watch']['mutated_existing_pitcher_count'] == 0
    assert payload['mutation_watch']['mutated_existing_pitcher_fields'] == []
    assert payload['verification_results']['no_existing_pitcher_row_was_mutated'] is True
    db.session.expire_all()
    assert {row.id: (row.full_name, row.team_id, row.active, row.position)
            for row in db.session.query(Pitcher).all()} == before


# ══ 39-43. The reused execution ledger ═══════════════════════════════════════
def test_39_the_ledger_row_is_inserted_in_the_same_transaction(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert payload['mutation_watch']['created_ledger_row_count'] == 1
    assert payload['mutation_watch']['created_object_types'] == [
        'OfficialPitchingLineRepairExecution']
    assert payload['verification_results'][
        'exactly_one_ledger_row_was_created'] is True
    rows = _festa_ledger_rows(approved.contract)
    assert len(rows) == 1
    # The authoritative committed id is read from the row, never assumed.
    assert payload['execution_ledger_id'] == int(rows[0].id)
    assert payload['execution_ledger_row']['id'] == int(rows[0].id)


def test_40_the_ledger_counts_equal_zero_zero_one_one(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    row = _festa_ledger_rows(approved.contract)[0]
    assert (row.identity_action_count, row.insert_action_count,
            row.update_action_count, row.total_action_count) == (0, 0, 1, 1)
    assert row.capability == festa.CAPABILITY
    assert row.status == Ledger.STATUS_COMPLETED
    assert row.season == 2026
    assert row.as_of_date == AS_OF
    assert row.accepted_baseline_version == 'v2'
    assert row.amendment_id == 'post_repair_matt_festa_earned_runs_2026'
    assert row.regenerated_manifest_fingerprint == approved.plan[
        'repair_manifest_fingerprint']
    assert row.apply_git_sha == 'f' * 40
    assert row.planner_git_sha
    assert row.started_at is not None
    assert row.completed_at is not None
    assert row.committed_at is not None
    assert row.precondition_summary and row.execution_summary and row.verification_summary
    # The original row is untouched and still alone on its own fingerprint.
    original = (db.session.query(Ledger)
                .filter(Ledger.approved_manifest_fingerprint
                        == ORIGINAL['approved_manifest_fingerprint']).all())
    assert len(original) == 1
    assert original[0].total_action_count == 675
    assert original[0].id != row.id


def test_41_any_in_transaction_failure_writes_no_game_log_change_and_no_ledger(
        approved, monkeypatch):
    real = festa._direct_readback

    def _wrong(session, log_id):
        readback = real(session, log_id)
        readback['raw'] = dict(readback['raw'], earned_runs=0)
        return readback

    monkeypatch.setattr(festa, '_direct_readback', _wrong)
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_VERIFICATION)
    assert payload['result'] == festa.RESULT_FAIL
    assert payload['rollback_performed'] is True
    assert 'earned_runs_is_exactly_one' in payload['abort_detail'][
        'failed_verifications']
    assert _stored().earned_runs == 0
    assert _festa_ledger_rows(approved.contract) == []


def test_42_a_successful_transaction_commits_both_the_row_and_the_ledger(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert payload['exit_code'] == 0
    assert payload['transaction_committed'] is True
    assert payload['database_writes_performed'] is True
    assert payload['rollback_performed'] is False
    assert payload['decision_reasons'] == [
        'reviewed_matt_festa_correction_applied_and_verified']
    db.session.remove()
    assert _stored().earned_runs == 1
    assert len(_festa_ledger_rows(approved.contract)) == 1


def test_43_re_execution_is_impossible_through_the_fingerprint_constraint(approved):
    first = _apply(approved)
    assert first['result'] == festa.RESULT_PASS
    second = _apply(approved)
    # The corrected row no longer disagrees with official scoring, so the regenerated plan
    # is empty and the second run refuses at the FIRST gate — before the ledger check that
    # would also have refused it. Either way it writes nothing.
    _assert_refused_without_writes(second)
    assert second['planner_verification']['checks'][
        'exactly_one_action_planned'] is False
    assert _stored().earned_runs == 1
    assert int(_stored().stat_correction_count) == 1
    assert len(_festa_ledger_rows(approved.contract)) == 1
    # And the database itself refuses a second row for the same approved fingerprint.
    with pytest.raises(sa.exc.IntegrityError):
        seed_original_ledger(
            capability=festa.CAPABILITY,
            approved_manifest_fingerprint=approved.contract[
                'approved_manifest_fingerprint'],
            regenerated_manifest_fingerprint=approved.contract[
                'approved_manifest_fingerprint'],
            identity_action_count=0, insert_action_count=0, update_action_count=1,
            total_action_count=1)
    db.session.rollback()


# ══ 44-46. Post-commit verification ══════════════════════════════════════════
def test_44_post_commit_completeness_passes_after_the_correction(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    post = payload['post_commit_verification']
    assert post['passed'] is True
    assert post['failed_checks'] == []
    assert post['not_executed_checks'] == []
    check = post['checks']['official_pitching_line_completeness_2026']
    assert check['executed'] is True
    assert check['execution_state'] == repair_apply.CHECK_EXECUTED
    assert check['passed'] is True
    assert check['observed']['stat_mismatch_count'] == 0
    assert check['observed']['exact_match_count'] == check['observed'][
        'official_pitching_lines']


def test_45_post_commit_local_aggregation_passes(approved):
    payload = _apply(approved)
    check = payload['post_commit_verification']['checks'][
        'canonical_season_bullpen_aggregation_local_only']
    assert check['passed'] is True
    assert check['checks']['thirty_complete_teams'] is True
    assert check['checks']['zero_partial_teams'] is True
    assert check['checks']['zero_unavailable_teams'] is True
    # Local-only cannot evaluate an official-validation reconciliation, and does not
    # pretend to: it is reported non-applicable rather than failed.
    reconciliation = check['reconciliations']
    assert reconciliation['satisfied'] is True
    assert reconciliation['failed'] == []
    assert reconciliation['non_applicable']['all_mandatory_metrics_match'][
        'applicable'] is False


def test_46_post_commit_official_validation_passes(approved):
    payload = _apply(approved)
    check = payload['post_commit_verification']['checks'][
        'canonical_season_bullpen_aggregation_official_validation']
    assert check['passed'] is True
    for name in ('all_thirty_teams_matched', 'zero_teams_mismatched',
                 'zero_mandatory_metric_mismatches',
                 'zero_unavailable_official_evidence', 'zero_missing_unique_starters',
                 'zero_multiple_starter_contradictions'):
        assert check['checks'][name] is True
    assert check['reconciliations']['satisfied'] is True


def test_46b_a_post_commit_failure_reports_fail_without_undoing_the_commit(
        approved, monkeypatch):
    monkeypatch.setattr(
        aggregation, 'run_aggregation',
        lambda **kwargs: dict(_clean_aggregation(**kwargs), result='fail', exit_code=1))
    payload = _apply(approved)
    assert payload['transaction_committed'] is True
    assert payload['database_writes_performed'] is True
    assert payload['result'] == festa.RESULT_FAIL
    assert payload['exit_code'] == 1
    assert payload['decision_reasons'] == ['post_commit_verification_failed']
    assert payload['failed_checks']
    # A committed correction is NOT undone by a failed post-commit check.
    assert _stored().earned_runs == 1
    assert len(_festa_ledger_rows(approved.contract)) == 1
    for gate in festa.DOWNSTREAM_GATES:
        assert payload[gate] == festa.GATE_BLOCKED


def test_46c_a_post_commit_check_that_could_not_run_has_not_passed(
        approved, monkeypatch):
    def _explode(**kwargs):  # noqa: ARG001
        raise RuntimeError('fixture')

    monkeypatch.setattr(aggregation, 'run_aggregation', _explode)
    payload = _apply(approved)
    post = payload['post_commit_verification']
    assert post['not_executed_checks'] == [
        'canonical_season_bullpen_aggregation_local_only',
        'canonical_season_bullpen_aggregation_official_validation']
    for name in post['not_executed_checks']:
        check = post['checks'][name]
        assert check['executed'] is False
        assert check['execution_state'] == repair_apply.CHECK_NOT_EXECUTED
        assert check['passed'] is False
    assert payload['result'] == festa.RESULT_FAIL
    assert set(post['not_executed_checks']) <= set(payload['unresolved_issues'])


# ══ 47. The existing closeout still isolates the original fingerprint ════════
def test_47_closeout_still_isolates_and_validates_the_original_fingerprint(approved):
    # The Brandyn Garcia row as the closed repair committed it, operation id included.
    db.session.query(GameLog).filter(GameLog.id == BR_LOG_ID).update(
        {'last_stat_correction_sync_run_id': 12345}, synchronize_session=False)
    db.session.commit()

    before = closeout.verify_execution_ledger(db.session)
    assert before['passed'] is True

    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert db.session.query(Ledger).count() == 2

    after = closeout.verify_execution_ledger(db.session)
    assert after['passed'] is True
    # A second ledger row exists, on a DIFFERENT approved fingerprint, and the closeout
    # still isolates exactly one row for the original one.
    assert after['observed']['ledger_row_count'] == 1
    assert after['observed']['completed_row_count'] == 1
    assert after['observed']['total_action_count'] == 675
    assert after['observed']['capability'] == 'official_pitching_line_repair_apply_2026_v1'
    assert after['checks']['exactly_one_ledger_row_for_the_approved_fingerprint'] is True
    assert after['observed'] == before['observed']
    amendment = closeout.verify_reviewed_amendment_row(db.session)
    assert amendment['passed'] is True
    assert amendment['observed']['hits_allowed'] == 0


# ══ 48. Downstream gates ═════════════════════════════════════════════════════
def test_48_every_downstream_gate_remains_blocked(approved):
    assert festa.DOWNSTREAM_GATES == (
        'foundation_3b_gate', 'public_reader_gate', 'team_state_performance_gate',
        'share_card_performance_gate', 'sc_05_gate')
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    for gate in festa.DOWNSTREAM_GATES:
        assert payload[gate] == festa.GATE_BLOCKED == 'blocked'
        assert payload['downstream_gate_statuses'][gate] == 'blocked'


def test_48b_a_refused_run_also_keeps_every_gate_blocked(approved, monkeypatch):
    monkeypatch.setattr(festa, 'IMMUTABLE_CONTRACT',
                        dict(approved.contract,
                             approved_manifest_fingerprint='0' * 64))
    payload = _apply(approved)
    for gate in festa.DOWNSTREAM_GATES:
        assert payload[gate] == 'blocked'
        assert payload['downstream_gate_statuses'][gate] == 'blocked'


# ══ 49-53. The dispatch-only workflow ════════════════════════════════════════
# Deliberately dependency-free: PyYAML is not in backend/requirements.txt, so a test that
# imported it would pass locally and fail on collection in CI. The workflow's list structure
# is regular enough to walk directly, and walking it is what makes the ordering claim a
# POSITION comparison rather than a substring comparison.
def _apply_job_steps():
    """The ordered step bodies of ``jobs.apply.steps``, parsed positionally."""
    lines = WORKFLOW_PATH.read_text(encoding='utf-8').splitlines()
    start = next((index for index, line in enumerate(lines)
                  if line.startswith('  apply:')), None)
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


def _workflow_shell():
    """Every line of the workflow outside the embedded summary heredoc.

    The heredoc is Python that writes human prose into the job summary; guarding against
    shell loops means guarding the SHELL, not the sentences it prints.
    """
    shell, inside = [], False
    for line in WORKFLOW_PATH.read_text(encoding='utf-8').splitlines():
        if "<<'PY'" in line:
            inside = True
            continue
        if inside:
            if line.strip() == 'PY':
                inside = False
            continue
        if line.lstrip().startswith('#'):
            continue
        shell.append(line)
    return '\n'.join(shell)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


def test_49_the_workflow_is_dispatch_only(workflow_text):
    assert 'workflow_dispatch:' in workflow_text
    for banned in ('schedule:', 'on: push', 'push:', 'pull_request:',
                   'repository_dispatch:', 'workflow_call:', 'workflow_run:'):
        assert banned not in workflow_text, banned
    # The only operator input is the confirmation phrase.
    inputs_block = workflow_text.split('inputs:', 1)[1].split('concurrency:', 1)[0]
    assert 'confirm_apply:' in inputs_block
    assert 'required: true' in inputs_block
    # Exactly one dispatch input is DECLARED. Compared against the declared key names, not
    # the surrounding description prose, so a governed word appearing in an explanation is
    # not mistaken for an input the workflow accepts.
    declared = re.findall(r'^      ([a-z_]+):$', inputs_block, re.M)
    assert declared == ['confirm_apply']
    for banned in ('season', 'as_of_date', 'team_id', 'game_pk', 'plan_scope',
                   'preview_limit', 'fingerprint', 'action_count', 'field', 'value',
                   'force', 'override'):
        assert banned not in declared, banned
    assert 'group: official-pitching-line-matt-festa-apply-2026' in workflow_text
    assert 'cancel-in-progress: false' in workflow_text
    assert 'contents: read' in workflow_text
    # A concurrency group of its own, so it never serializes against the closed repair.
    original = ORIGINAL_WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'group: official-pitching-line-matt-festa-apply-2026' not in original


def test_50_the_workflow_validates_the_confirmation_before_checkout(workflow_text):
    steps = _apply_job_steps()
    assert 'Validate apply confirmation' in steps[0]
    assert 'uses:' not in steps[0]
    assert festa.CONFIRMATION_PHRASE in steps[0]
    checkout = _step_index(steps, 'actions/checkout')
    python_setup = _step_index(steps, 'actions/setup-python')
    install = _step_index(steps, 'pip install')
    apply_step = _step_index(steps, 'run_official_pitching_line_matt_festa_apply_2026.py')
    assert 0 < checkout < python_setup < install < apply_step
    # Secrets are presence-checked, never printed.
    assert '-z "${DATABASE_URL:-}"' in steps[0]
    for secret in ('DATABASE_URL', 'SECRET_KEY', 'ADMIN_API_TOKEN'):
        assert f'echo ${secret}' not in workflow_text
        assert f'echo "${secret}"' not in workflow_text
        assert f'${{{{ secrets.{secret} }}}}' not in ' '.join(steps)


def test_51_the_workflow_invokes_the_apply_exactly_once(workflow_text):
    body = '\n'.join(line for line in workflow_text.splitlines()
                     if not line.lstrip().startswith('#'))
    assert body.count('run_official_pitching_line_matt_festa_apply_2026.py') == 1
    assert 'run_official_pitching_line_repair_apply_2026.py' not in body
    assert 'run_official_pitching_line_repair_closeout_2026.py' not in body
    assert 'exit "$apply_exit_code"' in body


def test_52_the_workflow_has_no_retry_loop_or_redispatch(workflow_text):
    shell = _workflow_shell().lower()
    for forbidden in ('retry', 'until ', 'while ', 'for i in', 'for ((', 'sleep ',
                      'gh workflow run', 'gh run rerun', 'curl ', 'workflow_run',
                      'repository_dispatch', 'nick-fields/retry', 'continue-on-error',
                      'schedule:'):
        assert forbidden not in shell, forbidden


def test_53_the_workflow_uploads_one_private_complete_artifact(workflow_text):
    steps = _apply_job_steps()
    uploads = [body for body in steps if 'actions/upload-artifact' in body]
    assert len(uploads) == 1
    assert 'retention-days: 30' in uploads[0]
    assert 'if-no-files-found: error' in uploads[0]
    assert 'matt-festa' in uploads[0]
    assert 'if: ${{ always() }}' in uploads[0]
    apply_step = steps[_step_index(
        steps, 'run_official_pitching_line_matt_festa_apply_2026.py')]
    assert '--output "$report_json"' in apply_step
    assert '--compact' in apply_step
    # Artifacts are private unless published; nothing here publishes one.
    assert 'public' not in uploads[0].lower()


# ══ 54-56. No migration, no cross-execution, no dispatch ═════════════════════
def test_54_no_migration_is_added():
    revisions = sorted(path.name for path in MIGRATIONS_DIR.glob('*.py'))
    assert any(LEDGER_REVISION in name for name in revisions)
    assert repair_apply.REPAIR_LEDGER_MIGRATION_REVISION == LEDGER_REVISION
    assert festa.REPAIR_LEDGER_MIGRATION_REVISION == LEDGER_REVISION
    # The dedicated capability reuses the existing ledger table and adds no model.
    source = SERVICE_PATH.read_text(encoding='utf-8')
    tree = ast.parse(source)
    assert not [node for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef)
                and any(ast.unparse(base).endswith('Model') for base in node.bases)]
    assert 'OfficialPitchingLineRepairExecution' in source


def test_55_the_original_apply_service_cannot_execute_this_fingerprint():
    original_source = ORIGINAL_SERVICE_PATH.read_text(encoding='utf-8')
    assert festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 not in original_source
    assert festa.CONFIRMATION_PHRASE not in original_source
    assert festa.ADVISORY_LOCK_CONTRACT not in original_source
    assert festa.CAPABILITY not in original_source
    original_workflow = ORIGINAL_WORKFLOW_PATH.read_text(encoding='utf-8')
    assert festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 not in original_workflow
    assert festa.CONFIRMATION_PHRASE not in original_workflow
    # The original approved contract is pinned to the 675-action manifest and its counts.
    contract = repair_apply.APPROVED_EXECUTION_CONTRACT
    assert contract['manifest_fingerprint'] == ORIGINAL['approved_manifest_fingerprint']
    assert contract['total_action_count'] == 675
    # And the reverse: this capability does not know the original phrase or fingerprint
    # as anything it could execute.
    assert festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 != (
        ORIGINAL['approved_manifest_fingerprint'])


def test_56_no_production_workflow_is_dispatched_by_the_implementation(workflow_text):
    for path in (SERVICE_PATH, CLI_PATH):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported = {alias.name.split('.')[0] for node in ast.walk(tree)
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                    for alias in node.names}
        imported |= {node.module.split('.')[0] for node in ast.walk(tree)
                     if isinstance(node, ast.ImportFrom) and node.module}
        for forbidden in ('requests', 'urllib', 'httpx', 'subprocess', 'socket'):
            assert forbidden not in imported, (path, forbidden)
    body = '\n'.join(line for line in workflow_text.splitlines()
                     if not line.lstrip().startswith('#'))
    assert 'workflow_dispatch:' in body
    assert 'gh workflow' not in body
    assert 'actions/github-script' not in body


# ═════════════════════════════════════════════════════════════════════════════
# PLANNER PROVENANCE AND THE COMPLETE REVIEWED PLAN ENVELOPE
#
# Three DIFFERENT commits are three different facts and must never collapse into one:
#   approved_planner_git_sha      where the reviewed plan and fingerprint were generated
#   regenerated_planner_git_sha   where the planner ran at apply time (necessarily later)
#   apply_git_sha                 the deployed commit executing the correction
# What is REQUIRED at runtime is not SHA equality — impossible once this capability merges
# — but that the planner IMPLEMENTATION is byte-identical to the reviewed one.
# ═════════════════════════════════════════════════════════════════════════════
APPROVED_PLAN_COMMIT = 'c4a0b3e4e33d64c5cecea3151ff3c30df7e0c5fa'
PLANNER_SOURCE_PATH = (REPO_ROOT / 'backend' / 'services'
                       / 'official_pitching_line_repair_plan_2026.py')


def test_p1_the_approved_planner_git_sha_is_pinned_to_the_plan_generation_commit():
    assert festa.IMMUTABLE_CONTRACT['approved_planner_git_sha'] == APPROVED_PLAN_COMMIT
    # It is pinned as a literal, not read from the runtime planner or the apply commit.
    tree = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert APPROVED_PLAN_COMMIT in literals


def test_p2_the_approved_planner_source_hash_matches_the_file_at_that_commit():
    approved = festa.IMMUTABLE_CONTRACT['approved_planner_source_sha256']
    assert len(approved) == 64
    # Hash the planner file the repository actually holds, whole-file and full-length.
    observed = hashlib.sha256(PLANNER_SOURCE_PATH.read_bytes()).hexdigest()
    assert observed == approved
    assert festa.planner_source_sha256() == approved
    assert festa.IMMUTABLE_CONTRACT['approved_planner_source_path'] == (
        'backend/services/official_pitching_line_repair_plan_2026.py')
    # No Git command decides this: a shallow clone or an absent repository directory must
    # not be able to turn the proof into a silent pass. Compared against the executable
    # statements only, so the function's own prose cannot satisfy or break the guard.
    tree = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    fn = next(node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name == 'planner_source_sha256')
    statements = [node for node in fn.body
                  if not (isinstance(node, ast.Expr)
                          and isinstance(node.value, ast.Constant))]
    body = '\n'.join(ast.unparse(node) for node in statements)
    for forbidden in ('git', 'subprocess', 'rev-parse', 'cat-file', 'popen', 'system('):
        assert forbidden not in body, forbidden
    assert 'sha256' in body and 'rb' in body


def test_p3_a_one_character_planner_source_change_refuses_before_writes(
        approved, monkeypatch, tmp_path):
    changed = tmp_path / 'planner_one_character_changed.py'
    original = PLANNER_SOURCE_PATH.read_bytes()
    changed.write_bytes(original[:-1] + b'#')          # exactly one byte different
    assert hashlib.sha256(changed.read_bytes()).hexdigest() != festa.planner_source_sha256()
    monkeypatch.setattr(planner, '__file__', str(changed))

    verification = festa.verify_planner_source()
    assert verification['planner_source_matches'] is False
    assert verification['failed'] == ['planner_source_matches_the_reviewed_source']

    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_PLANNER_SOURCE)
    assert payload['planner_source_matches'] is False
    assert payload['observed_planner_source_sha256'] != payload[
        'approved_planner_source_sha256']
    assert _stored().earned_runs == 0
    assert _festa_ledger_rows(approved.contract) == []


def test_p3b_an_unreadable_planner_source_refuses_before_writes(
        approved, monkeypatch, tmp_path):
    monkeypatch.setattr(planner, '__file__', str(tmp_path / 'does_not_exist.py'))
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_PLANNER_SOURCE)
    assert payload['observed_planner_source_sha256'] is None
    assert 'planner_source_was_readable' in payload['abort_detail']['failed']


def test_p4_the_approved_and_runtime_planner_shas_may_differ_safely(approved):
    # The planner reports whatever commit the deployed tree is at; nothing requires it to
    # equal the plan-generation commit, because after this capability merges it never can.
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert payload['approved_planner_git_sha'] == APPROVED_PLAN_COMMIT
    assert payload['planner_source_matches'] is True
    assert payload['observed_planner_source_sha256'] == payload[
        'approved_planner_source_sha256']
    # Nothing in the service demands equality of the two Git SHAs.
    tree = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.Eq):
            rendered = ast.unparse(node)
            assert not ('git_sha' in rendered and 'approved_planner_git_sha' in rendered), \
                rendered


def test_p4b_a_newer_runtime_planner_sha_still_applies(approved, monkeypatch):
    real = planner.run_repair_plan

    def _newer(**kwargs):
        return dict(real(**kwargs), git_sha='9' * 40)

    monkeypatch.setattr(planner, 'run_repair_plan', _newer)
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert payload['regenerated_planner_git_sha'] == '9' * 40
    assert payload['approved_planner_git_sha'] == APPROVED_PLAN_COMMIT
    assert payload['regenerated_planner_git_sha'] != payload['approved_planner_git_sha']
    row = _festa_ledger_rows(approved.contract)[0]
    assert row.planner_git_sha == APPROVED_PLAN_COMMIT
    assert row.execution_summary['regenerated_planner_git_sha'] == '9' * 40


def test_p5_the_ledger_planner_git_sha_records_the_plan_generation_commit(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    row = _festa_ledger_rows(approved.contract)[0]
    assert row.planner_git_sha == APPROVED_PLAN_COMMIT
    # And it is not silently the runtime value.
    assert row.planner_git_sha != row.execution_summary['regenerated_planner_git_sha'] \
        or festa.planner_source_sha256() is not None


def test_p6_the_ledger_apply_git_sha_records_the_apply_commit(approved):
    payload = _apply(approved)
    row = _festa_ledger_rows(approved.contract)[0]
    assert row.apply_git_sha == 'f' * 40
    assert payload['apply_git_sha'] == 'f' * 40
    assert row.apply_git_sha != row.planner_git_sha


def test_p7_the_runtime_planner_sha_and_source_hashes_are_kept_in_execution_summary(
        approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    summary = _festa_ledger_rows(approved.contract)[0].execution_summary
    assert summary['regenerated_planner_git_sha'] == approved.plan.get('git_sha')
    assert summary['approved_planner_source_sha256'] == festa.IMMUTABLE_CONTRACT[
        'approved_planner_source_sha256']
    assert summary['observed_planner_source_sha256'] == festa.planner_source_sha256()
    assert summary['observed_planner_source_sha256'] == summary[
        'approved_planner_source_sha256']


def test_p8_the_exact_reviewed_planner_inputs_pass(approved):
    verification = festa.verify_regenerated_plan(approved.plan)
    assert verification['failed'] == []
    assert verification['checks'][
        'planner_inputs_are_exactly_the_reviewed_inputs'] is True
    assert verification['observed']['planner_inputs'] == {
        'season': 2026, 'as_of_date': '2026-07-25', 'game_type': 'R',
        'team_id': 114, 'game_pk': 822952}


@pytest.mark.parametrize('field,value', [
    ('season', 2025),
    ('as_of_date', '2026-07-24'),
    ('game_type', 'P'),
    ('team_id', 999),
    ('game_pk', 999999),
])
def test_p9_to_p13_any_wrong_planner_input_refuses(approved, field, value):
    plan = copy.deepcopy(approved.plan)
    plan['inputs'][field] = value
    verification = festa.verify_regenerated_plan(plan)
    assert 'planner_inputs_are_exactly_the_reviewed_inputs' in verification['failed']


def test_p9b_a_wrong_scope_refuses_the_whole_run_before_writes(approved, monkeypatch):
    real = planner.run_repair_plan

    def _wrong_season(**kwargs):
        plan = copy.deepcopy(real(**kwargs))
        plan['inputs']['season'] = 2025
        return plan

    monkeypatch.setattr(planner, 'run_repair_plan', _wrong_season)
    payload = _apply(approved)
    assert 'planner_inputs_are_exactly_the_reviewed_inputs' in payload[
        'planner_verification']['failed']
    _assert_refused_without_writes(payload, reason=festa.ABORT_PLAN_CONTRACT)
    assert _stored().earned_runs == 0


@pytest.mark.parametrize('key,value,failing', [
    ('mode', 'apply', 'planner_mode_is_read_only'),
    ('mode', None, 'planner_mode_is_read_only'),
    ('exit_code', 0, 'planner_exit_code_is_the_reviewed_exit_code'),
    ('exit_code', 1, 'planner_exit_code_is_the_reviewed_exit_code'),
    ('repair_apply_gate', 'ready_for_apply',
     'generic_repair_apply_gate_is_still_blocked_for_a_subset'),
    ('database_writes_performed', True, 'planner_performed_no_writes'),
])
def test_p14_p15_p21_a_wrong_plan_envelope_field_refuses(approved, key, value, failing):
    plan = dict(approved.plan)
    plan[key] = value
    verification = festa.verify_regenerated_plan(plan)
    assert failing in verification['failed']


def test_p16_decision_reasons_exactly_the_reviewed_reason_passes(approved):
    assert approved.plan['decision_reasons'] == ['accepted_baseline_drift']
    verification = festa.verify_regenerated_plan(approved.plan)
    assert verification['checks'][
        'decision_reasons_are_exactly_the_reviewed_reasons'] is True
    assert verification['failed'] == []


def test_p17_an_additional_decision_reason_refuses(approved):
    # The expected reason is PRESENT, and it still refuses: exact equality, not membership.
    plan = dict(approved.plan,
                decision_reasons=['accepted_baseline_drift', 'another_reason'])
    verification = festa.verify_regenerated_plan(plan)
    assert 'accepted_baseline_drift' in plan['decision_reasons']
    assert 'decision_reasons_are_exactly_the_reviewed_reasons' in verification['failed']
    # Order is part of the comparison too.
    reordered = dict(approved.plan,
                     decision_reasons=['another_reason', 'accepted_baseline_drift'])
    assert 'decision_reasons_are_exactly_the_reviewed_reasons' in \
        festa.verify_regenerated_plan(reordered)['failed']


def test_p18_a_missing_baseline_drift_reason_refuses(approved):
    for reasons in ([], ['something_else']):
        plan = dict(approved.plan, decision_reasons=reasons)
        assert 'decision_reasons_are_exactly_the_reviewed_reasons' in \
            festa.verify_regenerated_plan(plan)['failed']


def test_p19_a_non_empty_blocking_counts_map_refuses(approved):
    assert approved.plan['blocking_counts_by_reason'] == {}
    plan = dict(approved.plan,
                blocking_counts_by_reason={'official_evidence_unavailable': 1})
    assert 'zero_blocking_reasons_anywhere_in_the_plan' in \
        festa.verify_regenerated_plan(plan)['failed']


def test_p20_a_non_empty_duplicate_action_id_list_refuses(approved):
    assert approved.plan['duplicate_action_ids'] == []
    plan = dict(approved.plan,
                duplicate_action_ids=['gamelog:update:44140:822952:670036'])
    assert 'no_duplicate_action_ids_reported_by_the_planner' in \
        festa.verify_regenerated_plan(plan)['failed']


def test_p22_the_existing_exact_one_action_contract_still_passes(approved):
    verification = festa.verify_regenerated_plan(approved.plan)
    assert verification['failed'] == []
    assert verification['failed_action_fields'] == []
    assert all(verification['checks'].values())
    assert all(verification['action_checks'].values())
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    assert payload['mutation_watch']['mutated_game_log_stat_fields'] == ['earned_runs']


def test_p23_the_approved_fingerprint_is_unchanged():
    assert festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 == (
        '903766c4d71652d102410d924d1adf2479f21b07a6742e2ce407385a06ac8f2b')


def test_p24_the_confirmation_phrase_is_unchanged():
    assert festa.CONFIRMATION_PHRASE == 'APPLY-2026-MATT-FESTA-ER-903766C4'
    assert festa.CONFIRMATION_PHRASE in CLI_PATH.read_text(encoding='utf-8')
    assert festa.CONFIRMATION_PHRASE in WORKFLOW_PATH.read_text(encoding='utf-8')


def test_p25_no_additional_field_became_writable(approved):
    assert festa.APPROVED_MUTABLE_FIELD == 'earned_runs'
    assert festa.APPROVED_VALUE_BEFORE == 0 and festa.APPROVED_VALUE_AFTER == 1
    before = {row.id: {column.name: getattr(row, column.name)
                       for column in GameLog.__table__.columns}
              for row in db.session.query(GameLog).all()}
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    db.session.expire_all()
    mutable = set(festa.CORRECTION_METADATA_FIELDS) | {festa.APPROVED_MUTABLE_FIELD}
    for row in db.session.query(GameLog).all():
        for column in GameLog.__table__.columns:
            name = column.name
            if row.id == FESTA_LOG_ID and name in mutable:
                continue
            assert getattr(row, name) == before[row.id][name], (row.id, name)


def test_p26_no_migration_is_added_by_the_provenance_work():
    revisions = sorted(path.name for path in MIGRATIONS_DIR.glob('*.py'))
    assert any(LEDGER_REVISION in name for name in revisions)
    # The provenance evidence lives in the existing JSON summary column, not a new column.
    columns = set(Ledger.__table__.columns.keys())
    for absent in ('regenerated_planner_git_sha', 'approved_planner_source_sha256',
                   'observed_planner_source_sha256', 'planner_source_matches'):
        assert absent not in columns, absent
    assert {'planner_git_sha', 'apply_git_sha', 'execution_summary'} <= columns


def test_p27_no_workflow_is_dispatched_by_the_provenance_work(workflow_text):
    body = '\n'.join(line for line in workflow_text.splitlines()
                     if not line.lstrip().startswith('#'))
    assert 'workflow_dispatch:' in body
    for forbidden in ('schedule:', 'push:', 'pull_request:', 'repository_dispatch:',
                      'workflow_run:', 'gh workflow', 'actions/github-script'):
        assert forbidden not in body, forbidden


def test_p28_every_downstream_gate_remains_blocked_across_the_new_refusals(
        approved, monkeypatch, tmp_path):
    # Scoped contexts, NOT monkeypatch.undo(): undo() would also revert the `approved`
    # fixture's own patches, which share this monkeypatch instance.
    with monkeypatch.context() as patched:
        real = planner.run_repair_plan
        patched.setattr(planner, 'run_repair_plan', lambda **kwargs: dict(
            real(**kwargs),
            decision_reasons=['accepted_baseline_drift', 'another_reason']))
        envelope_refusal = _apply(approved)
    assert envelope_refusal['result'] != festa.RESULT_PASS
    for gate in festa.DOWNSTREAM_GATES:
        assert envelope_refusal[gate] == 'blocked'
        assert envelope_refusal['downstream_gate_statuses'][gate] == 'blocked'

    with monkeypatch.context() as patched:
        changed = tmp_path / 'planner_changed.py'
        changed.write_bytes(PLANNER_SOURCE_PATH.read_bytes() + b'\n')
        patched.setattr(planner, '__file__', str(changed))
        source_refusal = _apply(approved)
    _assert_refused_without_writes(source_refusal, reason=festa.ABORT_PLANNER_SOURCE)
    for gate in festa.DOWNSTREAM_GATES:
        assert source_refusal[gate] == 'blocked'
        assert source_refusal['downstream_gate_statuses'][gate] == 'blocked'

    # Neither refusal wrote anything, so the reviewed state is intact and the real run
    # still succeeds — and still opens no gate.
    assert _stored().earned_runs == 0
    success = _apply(approved)
    assert success['result'] == festa.RESULT_PASS
    for gate in festa.DOWNSTREAM_GATES:
        assert success[gate] == 'blocked'
        assert success['downstream_gate_statuses'][gate] == 'blocked'


def test_p29_the_artifact_separates_the_three_provenance_facts(approved):
    payload = _apply(approved)
    assert payload['result'] == festa.RESULT_PASS
    for name in ('approved_planner_git_sha', 'regenerated_planner_git_sha',
                 'apply_git_sha', 'approved_planner_source_sha256',
                 'observed_planner_source_sha256', 'planner_source_matches',
                 'planner_source_verification'):
        assert name in payload, name
    assert payload['approved_planner_git_sha'] == APPROVED_PLAN_COMMIT
    assert payload['apply_git_sha'] == 'f' * 40
    assert payload['planner_source_matches'] is True
    observed = payload['planner_verification']['observed']
    for name in ('planner_mode', 'planner_exit_code', 'planner_inputs',
                 'repair_apply_gate', 'decision_reasons', 'blocking_counts_by_reason',
                 'duplicate_action_ids', 'database_writes_performed',
                 'regenerated_planner_git_sha'):
        assert name in observed, name
    assert observed['planner_mode'] == 'read_only'
    assert observed['planner_exit_code'] == 2
    assert observed['repair_apply_gate'] == 'blocked_subset_not_apply_eligible'
    assert observed['decision_reasons'] == ['accepted_baseline_drift']
    assert observed['blocking_counts_by_reason'] == {}
    assert observed['duplicate_action_ids'] == []
    # No credential, URL, or connection detail rides along with the new evidence.
    import json
    encoded = json.dumps(payload, default=str).lower()
    for forbidden in ('postgres://', 'postgresql://', 'password', 'secret_key',
                      'admin_api_token', 'database_url', 'sslmode'):
        assert forbidden not in encoded, forbidden


def test_p30_the_planner_source_check_runs_before_regeneration(approved, monkeypatch):
    """A changed planner never even produces a manifest to be compared."""
    calls = []
    real = planner.run_repair_plan

    def _counted(**kwargs):
        calls.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(planner, 'run_repair_plan', _counted)
    monkeypatch.setattr(festa, 'verify_planner_source', lambda: {
        'approved_planner_git_sha': APPROVED_PLAN_COMMIT,
        'approved_planner_source_path': 'x', 'approved_planner_source_sha256': 'a' * 64,
        'observed_planner_source_sha256': 'b' * 64, 'planner_source_matches': False,
        'checks': {'planner_source_matches_the_reviewed_source': False},
        'failed': ['planner_source_matches_the_reviewed_source']})
    payload = _apply(approved)
    _assert_refused_without_writes(payload, reason=festa.ABORT_PLANNER_SOURCE)
    assert calls == []
    assert payload['regenerated_manifest_fingerprint'] is None


def test_p31_the_generic_planner_is_not_made_apply_eligible_and_holds_no_approved_key():
    planner_source = PLANNER_SOURCE_PATH.read_text(encoding='utf-8')
    assert festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 not in planner_source
    assert festa.CONFIRMATION_PHRASE not in planner_source
    assert festa.CAPABILITY not in planner_source
    assert festa.IMMUTABLE_CONTRACT['approved_planner_source_sha256'] not in planner_source
    assert planner.PLAN_BLOCKED_SUBSET == 'diagnostic_subset_not_apply_eligible'
    assert planner.GATE_BLOCKED_SUBSET == 'blocked_subset_not_apply_eligible'


# ══ Artifact completeness and the read-only gate helpers ═════════════════════
def test_the_artifact_carries_every_required_field(approved):
    payload = _apply(approved)
    required = (
        'capability', 'mode', 'result', 'exit_code', 'decision_reasons', 'generated_at',
        'apply_git_sha', 'migration_head', 'immutable_approved_contract',
        'approved_manifest_fingerprint', 'regenerated_manifest_fingerprint',
        'planner_verification', 'regenerated_action', 'population_precondition',
        'original_repair_precondition', 'target_row_before',
        'correction_metadata_before', 'advisory_lock', 'mutation_watch',
        'dependent_evidence_invalidation', 'direct_readback', 'verification_results',
        'transaction_committed', 'rollback_performed', 'database_writes_performed',
        'target_row_after', 'correction_metadata_after', 'execution_ledger_row',
        'post_commit_verification', 'failed_checks', 'unresolved_issues',
        'downstream_gate_statuses')
    for name in required:
        assert name in payload, name
    observed = payload['planner_verification']['observed']
    assert observed['plan_scope'] == planner.PLAN_SCOPE_SUBSET
    assert observed['plan_status'] == planner.PLAN_BLOCKED_SUBSET
    assert observed['planner_result'] == planner.RESULT_INCONCLUSIVE
    assert observed['decision_reasons'] == [planner.BLOCK_BASELINE_DRIFT]
    assert payload['mode'] == 'apply'
    assert payload['capability'] == festa.CAPABILITY
    # No credential, URL, or connection detail is ever emitted.
    import json
    encoded = json.dumps(payload, default=str).lower()
    for forbidden in ('postgres://', 'postgresql://', 'password', 'secret_key',
                      'admin_api_token', 'database_url', 'sslmode'):
        assert forbidden not in encoded, forbidden


def test_the_read_only_gates_write_nothing(approved):
    from sqlalchemy import event

    statements = []

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        statements.append(statement)

    try:
        festa.verify_regenerated_plan(approved.plan)
        festa.verify_current_population(approved.diagnostic)
        festa.verify_original_repair(db.session)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    lowered = ' '.join(statements).lower()
    for forbidden in ('insert into', 'update ', 'delete from', 'truncate', 'drop table'):
        assert forbidden not in lowered, forbidden


def test_the_population_gate_names_the_reviewed_defect(approved):
    result = festa.verify_current_population(approved.diagnostic)
    assert result['failed'] == []
    assert result['defect_detail_count'] == 1
    assert result['stable_key'] == '822952:670036:114'
    assert result['checks']['local_earned_runs_is_zero'] is True
    assert result['checks']['official_earned_runs_is_one'] is True
    assert result['checks']['every_other_official_stat_already_agrees'] is True


def test_the_cli_refuses_a_wrong_phrase_before_importing_the_application():
    tree = ast.parse(CLI_PATH.read_text(encoding='utf-8'))
    main = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    body = ast.unparse(main)
    guard = body.index('CONFIRMATION_PHRASE')
    application_import = body.index('from app import app')
    assert guard < application_import
    # Nothing at module scope imports the application either.
    module_imports = {alias.name for node in tree.body
                      if isinstance(node, (ast.Import, ast.ImportFrom))
                      for alias in node.names}
    assert 'app' not in module_imports


def test_the_decision_record_exists_and_states_the_governed_facts():
    text = DECISION_RECORD.read_text(encoding='utf-8')
    assert festa.APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 in text
    assert ORIGINAL['approved_manifest_fingerprint'] in text
    assert 'diagnostic_subset_not_apply_eligible' in text
    assert festa.CONFIRMATION_PHRASE in text
    assert '44140' in text
