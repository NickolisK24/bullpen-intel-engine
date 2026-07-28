"""Brandyn Garcia exact-to-defective transition diagnostic (2026) — read-only forensics.

Covers reproduction of the current one-hit-versus-zero-hit mismatch, exact identity keying by
official MLB id, appearance-team authority, the refusal to use names or current team, the
contradiction cases (duplicate official lines, duplicate local rows, identity mismatch), the
durable-history search and its fail-closed default, the rule that current values alone can
never prove which side moved, and the read-only guarantee: the diagnostic never writes, never
repairs, never approves a fingerprint, and never touches the accepted defect baseline.
"""

from datetime import date, datetime
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import official_pitching_line_repair_plan_2026 as planner
from services import official_pitching_line_transition_diagnostic_2026 as diagnostic
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_PK = diagnostic.TARGET_GAME_PK              # 825058
PERSON = diagnostic.TARGET_OFFICIAL_MLB_PERSON_ID  # 805299
TEAM = diagnostic.TARGET_APPEARANCE_TEAM_ID      # 109
OPPONENT = 158
LOG_ID = diagnostic.TARGET_LOCAL_GAME_LOG_ID     # 43765
GDATE = diagnostic.TARGET_GAME_DATE              # 2026-07-20
STARTER = 700001
OPPOSING_STARTER = 700002

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = (REPO_ROOT / 'backend' / 'services'
                / 'official_pitching_line_transition_diagnostic_2026.py')
CLI_PATH = (REPO_ROOT / 'backend' / 'scripts'
            / 'run_official_pitching_line_transition_diagnostic_2026.py')
WORKFLOW_PATH = (REPO_ROOT / '.github' / 'workflows'
                 / 'official_pitching_line_transition_diagnostic.yml')
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


# ── Official evidence fakes ───────────────────────────────────────────────────
def _ip(outs):
    return f'{outs // 3}.{outs % 3}'


def _pline(mlb_id, *, gs, outs, hits, name):
    return (mlb_id, name, {
        'gamesStarted': gs, 'inningsPitched': _ip(outs), 'runs': 0, 'earnedRuns': 0,
        'hits': hits, 'baseOnBalls': 0, 'strikeOuts': 1, 'homeRuns': 0,
        'strikes': outs * 2, 'numberOfPitches': outs * 3,
    })


def _side(team_id, name, lines):
    return {
        'team': {'id': team_id, 'name': name, 'abbreviation': f'T{team_id}'},
        'pitchers': [mlb_id for mlb_id, _n, _s in lines],
        'players': {
            f'ID{mlb_id}': {'person': {'id': mlb_id, 'fullName': pname},
                            'stats': {'pitching': stats}}
            for mlb_id, pname, stats in lines
        },
    }


def _boxscore(*, garcia_hits=0, home_lines=None, away_lines=None):
    home = home_lines if home_lines is not None else [
        _pline(STARTER, gs=1, outs=18, hits=4, name='Home Starter'),
        _pline(PERSON, gs=0, outs=3, hits=garcia_hits, name='Brandyn Garcia'),
    ]
    away = away_lines if away_lines is not None else [
        _pline(OPPOSING_STARTER, gs=1, outs=15, hits=6, name='Away Starter'),
    ]
    return {'teams': {'home': _side(TEAM, 'Arizona Diamondbacks', home),
                      'away': _side(OPPONENT, f'Team{OPPONENT}', away)}}


class _FakeMlbClient:
    def __init__(self, boxscore=None, raise_boxscore=False):
        self.boxscore = boxscore if boxscore is not None else _boxscore()
        self.raise_boxscore = raise_boxscore
        self.boxscore_calls = []

    def get_game_boxscore(self, game_pk):
        self.boxscore_calls.append(game_pk)
        if self.raise_boxscore:
            raise RuntimeError('boxscore unavailable')
        return self.boxscore


# ── Local ledger fixtures ─────────────────────────────────────────────────────
def _pitcher(mlb_id=PERSON, *, name='Brandyn Garcia', current_team=None, row_id=None):
    row = Pitcher(id=row_id, mlb_id=mlb_id, full_name=name, active=True,
                  team_id=current_team)
    db.session.add(row)
    db.session.commit()
    return row


def _log(*, pitcher_row, hits=1, log_id=LOG_ID, game_pk=GAME_PK, team=TEAM,
         corrections=0, corrected_at=None, correction_source=None, correction_run=None):
    row = GameLog(
        id=log_id, pitcher_id=pitcher_row.id, mlb_game_pk=game_pk, game_date=GDATE,
        game_type='R', games_started=0, innings_pitched_outs=3, innings_pitched=1.0,
        runs_allowed=0, earned_runs=0, hits_allowed=hits, walks=0, strikeouts=1,
        home_runs_allowed=0, strikes=6, pitches_thrown=9,
        opponent=f'Team{OPPONENT}', opponent_abbreviation=f'T{OPPONENT}',
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_id=team, appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
        stat_correction_count=corrections, last_stat_correction_at=corrected_at,
        last_stat_correction_source=correction_source,
        last_stat_correction_sync_run_id=correction_run,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _seed(*, hits=1, **kwargs):
    """The production shape: local row says one hit, official says zero."""
    return _log(pitcher_row=_pitcher(), hits=hits, **kwargs)


def _run(client=None, **kwargs):
    return diagnostic.run_transition_diagnostic(
        client=client or _FakeMlbClient(),
        generated_at='2026-07-28T00:00:00Z', retrieved_at='2026-07-28T00:00:00Z',
        **kwargs)


def _citation(*, source_table, source_pk, field, value, created_at,
              source_family='game_log', evidence_object_id=None):
    """A durable evidence citation retaining a prior field value."""
    if evidence_object_id is None:
        obj = EvidenceObject(
            evidence_key=f'k:{source_pk}:{field}', evidence_type='workload',
            subject_type='pitcher', subject_id=str(PERSON), subject_key=f'p:{PERSON}',
            product_date=GDATE, claim_template_id='t1', rendered_claim='c',
            rule_id='workload.v1', rule_version=1, rule_definition_hash='h' * 64,
            typed_cited_inputs={}, computation_trace={}, completeness_state='complete',
            source='test',
        )
        db.session.add(obj)
        db.session.commit()
        evidence_object_id = obj.id
    row = EvidenceCitation(
        evidence_object_id=evidence_object_id, source_family=source_family,
        source_table=source_table, source_pk=str(source_pk),
        source_field_names=[field], citation_role='supporting_input',
        cited_values={field: value}, provenance={'captured_by': 'test'},
        created_at=created_at,
    )
    db.session.add(row)
    db.session.commit()
    return row


# ═══════════════ 1. Current mismatch reproduction ═══════════════════════════
def test_current_official_zero_versus_local_one_is_reproduced(app):
    _seed()
    payload = _run()
    comparison = payload['current_comparison']
    assert comparison['current_official_value'] == 0
    assert comparison['current_local_value'] == 1
    assert comparison['values_differ'] is True
    assert comparison['reason_code'] == 'hits_mismatch'
    assert comparison['matches_production_artifact_expectation'] is True
    recon = payload['reconciliations']
    assert recon['current_official_hits_is_zero'] is True
    assert recon['current_local_hits_allowed_is_one'] is True
    assert recon['current_mismatch_reason_is_hits_mismatch'] is True


def test_current_official_evidence_is_reported_in_full(app):
    _seed()
    payload = _run()
    official = payload['current_official_evidence']
    assert official['endpoint'] == f'/game/{GAME_PK}/boxscore'
    assert official['retrieved_at'] == '2026-07-28T00:00:00Z'
    assert official['official_mlb_person_id'] == PERSON
    assert official['official_team_id'] == TEAM
    assert official['official_team_name'] == 'Arizona Diamondbacks'
    assert official['opposing_team_id'] == OPPONENT
    assert official['official_role'] == 'relief'
    assert official['official_raw_hits'] == 0
    assert official['normalized_hits_allowed'] == 0
    assert official['innings_pitched'] == '1.0'
    assert official['innings_pitched_outs'] == 3
    assert official['official_raw_pitching_line']['strikes'] == 6
    assert len(official['source_fingerprint']) == 64


def test_current_local_evidence_is_reported_in_full(app):
    _seed(corrections=0)
    payload = _run()
    local = payload['current_local_evidence']
    assert local['id'] == LOG_ID
    assert local['mlb_game_pk'] == GAME_PK
    assert local['appearance_team_id'] == TEAM
    assert local['pitcher_mlb_id'] == PERSON
    assert local['hits_allowed'] == 1
    assert local['innings_pitched_outs'] == 3
    assert local['stat_correction_count'] == 0
    assert local['last_stat_correction_at'] is None
    assert local['created_at'] is not None
    # GameLog has no updated_at column, so a row rewrite is only recorded by correction
    # metadata. The diagnostic reports that structural fact rather than assuming it.
    assert local['updated_at_column_exists'] is False


# ═══════════════ 2-5. Identity keying ═══════════════════════════════════════
def test_exact_official_identity_key_is_required(app):
    _seed()
    # Same game, same team, but a different official person: no line matches the target.
    boxscore = _boxscore(home_lines=[
        _pline(STARTER, gs=1, outs=18, hits=4, name='Home Starter'),
        _pline(PERSON + 1, gs=0, outs=3, hits=0, name='Brandyn Garcia'),
    ])
    payload = _run(client=_FakeMlbClient(boxscore))
    assert payload['current_official_evidence']['matching_line_count'] == 0
    assert diagnostic.FAIL_OFFICIAL_LINE_ABSENT in payload['decision_reasons']
    assert payload['result'] == diagnostic.RESULT_FAIL


def test_appearance_team_109_is_required(app):
    _log(pitcher_row=_pitcher(), hits=1, team=OPPONENT)
    payload = _run()
    assert diagnostic.FAIL_APPEARANCE_TEAM_MISMATCH in payload['decision_reasons']
    assert payload['reconciliations']['appearance_team_equals_the_official_team'] is False
    assert payload['result'] == diagnostic.RESULT_FAIL


def test_name_matching_is_never_used(app):
    # A local identity with the right name but the wrong MLB id is NOT this person.
    _log(pitcher_row=_pitcher(mlb_id=PERSON + 5000, name='Brandyn Garcia'), hits=1)
    payload = _run()
    assert diagnostic.FAIL_LOCAL_IDENTITY_MISMATCH in payload['decision_reasons']
    assert payload['result'] == diagnostic.RESULT_FAIL
    assert payload['current_official_evidence']['identity_resolution'] == \
        'pitcher.mlb_id_exact_match'
    assert 'full_name' in payload['current_local_evidence']['identity_excluded_signals']
    source = SERVICE_PATH.read_text(encoding='utf-8')
    lookup = source.split('def _current_local_evidence')[1].split('def ')[0]
    assert 'Pitcher.id ==' in lookup
    assert 'full_name' not in lookup


def test_current_team_is_never_used(app):
    # A current team assignment that contradicts the historical appearance team.
    _log(pitcher_row=_pitcher(current_team=OPPONENT), hits=1)
    payload = _run()
    assert payload['current_local_evidence']['appearance_team_id'] == TEAM
    assert payload['reconciliations']['no_current_team_authority_was_used'] is True
    assert payload['reconciliations']['appearance_team_equals_the_official_team'] is True
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'Pitcher.team_id' not in source


# ═══════════════ 6-7. Contradictions ════════════════════════════════════════
def test_duplicate_official_lines_fail(app):
    _seed()
    # One official side listing the same person twice is a contradictory source.
    boxscore = _boxscore()
    players = boxscore['teams']['home']['players']
    players['ID_DUPLICATE'] = {
        'person': {'id': PERSON, 'fullName': 'Brandyn Garcia'},
        'stats': {'pitching': dict(players[f'ID{PERSON}']['stats']['pitching'])},
    }
    payload = _run(client=_FakeMlbClient(boxscore))
    assert diagnostic.FAIL_OFFICIAL_LINE_DUPLICATED in payload['decision_reasons']
    assert payload['result'] == diagnostic.RESULT_FAIL


def test_duplicate_local_rows_are_blocked_by_storage(app):
    """A duplicate ledger line for one identity and game cannot be stored at all."""
    row = _pitcher()
    _log(pitcher_row=row, hits=1)
    with pytest.raises(Exception) as excinfo:
        _log(pitcher_row=row, hits=1, log_id=LOG_ID + 1, game_pk=GAME_PK)
    assert 'unique' in str(excinfo.value).lower()
    db.session.rollback()


def test_duplicate_local_row_detection_is_keyed_on_the_identity_not_the_game(app):
    """The sibling check must not flag another pitcher's legitimate line in the same game."""
    _seed()
    other = _pitcher(mlb_id=STARTER, name='Home Starter')
    _log(pitcher_row=other, hits=4, log_id=LOG_ID + 1, game_pk=GAME_PK)
    payload = _run()
    assert payload['current_local_evidence']['duplicate_sibling_game_log_ids'] == []
    assert diagnostic.FAIL_LOCAL_ROW_DUPLICATED not in payload['decision_reasons']
    assert payload['reconciliations'][
        'exactly_one_local_game_log_matches_the_target'] is True


def test_unavailable_official_evidence_is_reported(app):
    _seed()
    payload = _run(client=_FakeMlbClient(raise_boxscore=True))
    assert payload['current_official_evidence']['official_evidence_available'] is False
    assert diagnostic.FAIL_OFFICIAL_EVIDENCE_UNAVAILABLE in payload['decision_reasons']
    assert payload['database_writes_performed'] is False


# ═══════════════ 8-11. Historical evidence ══════════════════════════════════
def test_missing_history_is_unprovable_and_inconclusive(app):
    """The expected production answer: the mismatch is real, its cause is not recoverable."""
    _seed(corrections=0)
    payload = _run()
    assert payload['authority_transition_classification'] == \
        diagnostic.TRANSITION_UNPROVABLE
    assert payload['confidence'] == diagnostic.CONFIDENCE_UNPROVABLE
    assert payload['result'] == diagnostic.RESULT_INCONCLUSIVE
    assert payload['exit_code'] == 2
    assert payload['official_change_evidence']['proves_official_change'] is False
    assert payload['local_change_evidence']['proves_local_change'] is False
    assert payload['unresolved_questions']
    # Absence of history must never be laundered into a claim that MLB changed the box score.
    assert payload['reconciliations'][
        'absence_of_history_is_not_reported_as_official_change'] is True


def test_current_evidence_alone_cannot_prove_which_side_changed(app):
    _seed()
    payload = _run()
    comparison = payload['current_comparison']
    assert comparison['values_differ'] is True          # the mismatch is real
    assert comparison['proves_which_side_changed'] is False
    assert comparison['why_not']
    assert payload['authority_transition_classification'] != \
        diagnostic.TRANSITION_OFFICIAL_CHANGED
    assert payload['result'] != diagnostic.RESULT_PASS


def test_official_change_is_reported_only_with_durable_prior_official_evidence(app):
    _seed()
    _citation(source_table='official_boxscore_pitching', source_pk=f'{GAME_PK}:{PERSON}',
              field='hits', value=1, created_at=datetime(2026, 7, 21, 6, 0),
              source_family='mlb_stats_api')
    payload = _run()
    official_change = payload['official_change_evidence']
    assert official_change['prior_official_value_retained'] is True
    assert official_change['prior_official_values'][0]['cited_value'] == 1
    assert official_change['prior_official_value_differs_from_current'] is True
    assert official_change['proves_official_change'] is True
    assert payload['authority_transition_classification'] == \
        diagnostic.TRANSITION_OFFICIAL_CHANGED
    assert payload['confidence'] == diagnostic.CONFIDENCE_PROVEN
    assert payload['result'] == diagnostic.RESULT_PASS


def test_local_change_is_reported_only_with_durable_prior_local_evidence(app):
    _seed(corrections=1, corrected_at=datetime(2026, 7, 22, 5, 0),
          correction_source='official_boxscore', correction_run=91)
    _citation(source_table='game_logs', source_pk=LOG_ID, field='hits_allowed', value=0,
              created_at=datetime(2026, 7, 21, 6, 0))
    payload = _run()
    local_change = payload['local_change_evidence']
    assert local_change['prior_local_value_retained'] is True
    assert local_change['prior_local_values'][0]['cited_value'] == 0
    assert local_change['prior_local_value_differs_from_current'] is True
    assert local_change['proves_local_change'] is True
    assert local_change['row_was_corrected_after_ingestion'] is True
    assert local_change['last_stat_correction_sync_run_id'] == 91
    assert payload['authority_transition_classification'] == \
        diagnostic.TRANSITION_LOCAL_CHANGED
    assert payload['result'] == diagnostic.RESULT_PASS


def test_both_sides_changing_is_classified_as_both(app):
    _seed(corrections=1, corrected_at=datetime(2026, 7, 22, 5, 0),
          correction_source='official_boxscore', correction_run=91)
    _citation(source_table='game_logs', source_pk=LOG_ID, field='hits_allowed', value=0,
              created_at=datetime(2026, 7, 21, 6, 0))
    _citation(source_table='official_boxscore_pitching', source_pk=f'{GAME_PK}:{PERSON}',
              field='hits', value=1, created_at=datetime(2026, 7, 21, 7, 0),
              source_family='mlb_stats_api')
    payload = _run()
    assert payload['authority_transition_classification'] == \
        diagnostic.TRANSITION_BOTH_CHANGED
    assert payload['result'] == diagnostic.RESULT_PASS


def test_a_correction_count_alone_does_not_prove_the_field_changed(app):
    """stat_correction_count increments per ROW, never per field."""
    _seed(corrections=1, corrected_at=datetime(2026, 7, 22, 5, 0),
          correction_source='official_boxscore', correction_run=91)
    payload = _run()
    local_change = payload['local_change_evidence']
    assert local_change['proves_row_was_rewritten'] is True    # a correction happened
    assert local_change['proves_local_change'] is False        # but not that hits moved
    assert payload['authority_transition_classification'] == \
        diagnostic.TRANSITION_UNPROVABLE
    assert payload['result'] == diagnostic.RESULT_INCONCLUSIVE
    assert any('which field' in q['question'] for q in payload['unresolved_questions'])


def test_a_matching_prior_value_does_not_prove_a_change(app):
    # A citation that agrees with the current value proves stability, not movement.
    _seed()
    _citation(source_table='game_logs', source_pk=LOG_ID, field='hits_allowed', value=1,
              created_at=datetime(2026, 7, 21, 6, 0))
    payload = _run()
    assert payload['local_change_evidence']['prior_local_value_retained'] is True
    assert payload['local_change_evidence']['prior_local_value_differs_from_current'] is False
    assert payload['local_change_evidence']['proves_local_change'] is False
    assert payload['authority_transition_classification'] == \
        diagnostic.TRANSITION_UNPROVABLE


def test_every_historical_source_is_named_and_checked(app):
    _seed()
    payload = _run()
    checked = payload['historical_evidence_sources_checked']
    for source in (diagnostic.SOURCE_CORRECTION_METADATA,
                   diagnostic.SOURCE_EVIDENCE_CITATIONS,
                   diagnostic.SOURCE_EVIDENCE_OBJECTS,
                   diagnostic.SOURCE_SYNC_RUNS,
                   diagnostic.SOURCE_POSTGAME,
                   diagnostic.SOURCE_SYNC_FAILURES,
                   diagnostic.SOURCE_REPO_ARTIFACTS,
                   diagnostic.SOURCE_OFFICIAL_SNAPSHOTS,
                   diagnostic.SOURCE_WORKFLOW_ARTIFACTS):
        assert source in checked, source
    detail = payload['historical_evidence_source_detail']
    # The two structurally absent sources are reported as limitations, not silent gaps.
    assert detail[diagnostic.SOURCE_OFFICIAL_SNAPSHOTS]['available'] is False
    assert detail[diagnostic.SOURCE_OFFICIAL_SNAPSHOTS]['reason']
    assert detail[diagnostic.SOURCE_WORKFLOW_ARTIFACTS]['available'] is False
    assert '14-day' in detail[diagnostic.SOURCE_WORKFLOW_ARTIFACTS]['reason'] or \
        '14 days' in detail[diagnostic.SOURCE_WORKFLOW_ARTIFACTS]['reason']


def test_historical_claims_must_carry_source_timestamp_and_value(app):
    _seed()
    _citation(source_table='game_logs', source_pk=LOG_ID, field='hits_allowed', value=0,
              created_at=datetime(2026, 7, 21, 6, 0))
    payload = _run()
    recon = payload['reconciliations']
    assert recon['every_historical_claim_identifies_a_durable_source'] is True
    assert recon['every_historical_claim_reports_a_timestamp'] is True
    assert recon['every_historical_claim_is_source_backed'] is True
    assert recon['historical_chronology_is_internally_consistent'] is True
    claim = payload['local_change_evidence']['prior_local_values'][0]
    assert claim['source_table'] == 'game_logs'
    assert claim['created_at'] == '2026-07-21T06:00:00'
    assert claim['cited_value'] == 0


def test_a_mismatch_that_no_longer_reproduces_is_not_a_finding(app):
    # Official now agrees with local: the transition question is not answered, it is moot.
    _seed(hits=1)
    payload = _run(client=_FakeMlbClient(_boxscore(garcia_hits=1)))
    assert payload['current_comparison']['values_differ'] is False
    assert payload['authority_transition_classification'] == \
        diagnostic.TRANSITION_NOT_REPRODUCED
    assert payload['confidence'] == diagnostic.CONFIDENCE_CONTRADICTED
    assert payload['result'] == diagnostic.RESULT_INCONCLUSIVE


# ═══════════════ 12-14. Baseline, repair, and fingerprint safety ════════════
def test_no_accepted_baseline_value_changes(app):
    before = dict(planner.ACCEPTED_DEFECT_BASELINE)
    _seed()
    payload = _run()
    assert dict(planner.ACCEPTED_DEFECT_BASELINE) == before
    assert before['exact_match_count'] == 12697          # not 12,696
    assert before['defective_matched_line_count'] == 159  # not 160
    assert before['defect_line_action_count'] == 604      # not 605
    assert payload['accepted_defect_baseline_modified'] is False
    assert payload['reconciliations'][
        'no_accepted_baseline_value_is_read_or_changed'] is True
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'ACCEPTED_DEFECT_BASELINE' not in source


def test_no_repair_action_is_applied(app):
    _seed()
    payload = _run()
    assert payload['repair_actions_applied'] == 0
    assert payload['repair_apply_gate'] == 'blocked'
    assert payload['reconciliations']['no_repair_action_is_applied'] is True


def test_no_fingerprint_is_approved(app):
    _seed()
    payload = _run()
    assert payload['approved_manifest_fingerprints'] == []
    assert set(payload['unapproved_manifest_fingerprints']) == {
        '9b8ab677c83ec5b8efa5a4020593911dc4d6d73e3262a09c0703d1a5907b49b7',
        'dd453cd63b1e4ccc14b5ff97c962635d6c5eda296a4e4ef63066105eeec225c6',
        '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b',
    }
    assert payload['reconciliations']['no_manifest_fingerprint_is_approved'] is True


# ═══════════════ 15-18. Read-only guarantees ════════════════════════════════
def test_database_remains_unchanged(app):
    _seed()
    before = {(r.id, r.hits_allowed, r.stat_correction_count)
              for r in db.session.query(GameLog).all()}
    pitchers_before = db.session.query(Pitcher).count()
    payload = _run()
    db.session.expire_all()
    assert {(r.id, r.hits_allowed, r.stat_correction_count)
            for r in db.session.query(GameLog).all()} == before
    assert db.session.query(Pitcher).count() == pitchers_before
    assert payload['database_writes_performed'] is False
    assert payload['mode'] == 'read_only'


def test_zero_write_sql_is_emitted(app):
    _seed()
    statements = []

    @event.listens_for(db.engine, 'before_cursor_execute')
    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        _run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    assert statements                                   # the diagnostic really queried
    for statement in statements:
        head = statement.strip().split(None, 1)[0].upper() if statement.strip() else ''
        assert head not in ('INSERT', 'UPDATE', 'DELETE'), statement


def test_no_apply_mode_exists():
    source = SERVICE_PATH.read_text(encoding='utf-8')
    cli = CLI_PATH.read_text(encoding='utf-8')
    for token in ('def apply', 'apply_repair', 'apply_manifest', 'session.commit',
                  'session.add', 'session.delete', 'session.execute'):
        assert token not in source, token
    for token in ('--apply', 'accept-fingerprint', 'accept_fingerprint'):
        assert token not in cli, token
    assert '--compact' in cli and '--output' in cli


def test_workflow_is_dispatch_only_and_read_only():
    workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
    header = workflow.split('jobs:', 1)[0]
    assert 'workflow_dispatch' in header
    for trigger in ('schedule:', 'push:', 'pull_request:'):
        assert trigger not in header, trigger
    for token in ('apply:', 'accept_fingerprint:', 'fingerprint_acceptance:'):
        assert token not in header, token
    assert 'permissions:' in workflow and 'contents: read' in workflow
    assert 'retention-days: 14' in workflow
    assert 'if-no-files-found: error' in workflow
    for mutation in ('db.session.commit', 'INSERT INTO', 'UPDATE ', 'DELETE FROM',
                     'flask db upgrade'):
        assert mutation not in workflow, mutation
    # Production bootstrap consistent with the governed diagnostics.
    for secret in ('secrets.DATABASE_URL', 'secrets.SECRET_KEY',
                   'secrets.BASEBALLOS_ADMIN_API_TOKEN'):
        assert secret in workflow, secret
    # The fixed target cannot be redirected from a workflow input.
    assert '825058:805299:109' in workflow
    assert 'game_pk:' not in header
    assert 'team_id:' not in header


def test_workflow_does_not_print_secret_values_or_lengths():
    workflow = WORKFLOW_PATH.read_text(encoding='utf-8')
    for leak in ('echo "$DATABASE_URL', 'echo $DATABASE_URL', 'echo "$SECRET_KEY',
                 'echo "$ADMIN_API_TOKEN', '${#DATABASE_URL}', '${#SECRET_KEY}',
                 '${#ADMIN_API_TOKEN}'):
        assert leak not in workflow, leak


def test_downstream_gates_remain_blocked(app):
    _seed()
    payload = _run()
    for gate in ('foundation_3b_gate', 'public_reader_gate', 'share_card_performance_gate',
                 'repair_apply_gate'):
        assert payload[gate] == 'blocked', gate


def test_report_has_every_required_field(app):
    _seed()
    payload = _run()
    for key in ('capability', 'mode', 'result', 'exit_code', 'generated_at', 'git_sha',
                'migration_head', 'target', 'current_official_evidence',
                'current_local_evidence', 'current_comparison',
                'historical_evidence_sources_checked', 'historical_evidence_found',
                'official_change_evidence', 'local_change_evidence',
                'authority_transition_classification', 'confidence',
                'unresolved_questions', 'decision_reasons', 'reconciliations',
                'database_writes_performed'):
        assert key in payload, key
    assert payload['capability'] == diagnostic.CAPABILITY
    assert payload['mode'] == 'read_only'
    assert payload['database_writes_performed'] is False
    assert payload['target']['mlb_game_pk'] == GAME_PK
    assert payload['target']['official_mlb_person_id'] == PERSON
    assert payload['target']['appearance_team_id'] == TEAM
    assert payload['target']['local_game_log_id'] == LOG_ID
    assert payload['target']['field'] == 'hits_allowed'
    assert set(payload['allowed_classifications']) == {
        'official_source_changed', 'local_game_log_changed', 'both_changed',
        'historical_state_unprovable', 'current_mismatch_not_reproduced'}


def test_result_is_deterministic_across_identical_runs(app):
    _seed()
    first = _run()
    second = _run()
    for key in ('result', 'authority_transition_classification', 'confidence',
                'decision_reasons', 'reconciliations'):
        assert first[key] == second[key], key
    assert (first['current_official_evidence']['source_fingerprint']
            == second['current_official_evidence']['source_fingerprint'])


def test_decision_record_documents_the_transition():
    text = DECISION_RECORD.read_text(encoding='utf-8').lower()
    for phrase in ('brandyn garcia', '805299', '825058', '43765', 'hits_allowed',
                   'historical_state_unprovable', '12,697', '12,696',
                   'official stat correction', 'local ingestion',
                   '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b'):
        assert phrase in text, phrase
