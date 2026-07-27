"""Official pitching-line completeness diagnostic (2026) — read-only.

Covers the typed classification vocabulary (exact match, missing official line, extra local
line, missing local/official identity, appearance-team mismatch, starter/relief mismatch,
per-stat mismatch, duplicate local line, missing/contradictory official starter, unavailable
official evidence), the official starter contract (`gamesStarted == 1` only), identity
matching by official MLB id (never by name), historical appearance-team authority (never
`Pitcher.team_id`), the reconciliations, the pass/fail/inconclusive result contract,
deterministic ordering and detail bounding, the CLI and dispatch-only workflow, and the
read-only guarantee: the diagnostic never mutates a row and never emits write SQL.
"""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import official_pitching_line_completeness_2026 as diag
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


A, B, C = 100, 200, 300
SEASON = 2026
AS_OF = date(2026, 7, 25)
GDATE = date(2026, 6, 10)
GAME_PK = 9001
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'official_pitching_line_completeness_2026.py'
CLI_PATH = REPO_ROOT / 'backend' / 'scripts' / 'run_official_pitching_line_completeness_2026.py'
WORKFLOW_PATH = (
    REPO_ROOT / '.github' / 'workflows' / 'official_pitching_line_completeness.yml')


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
def _pitcher(mlb_id, *, current_team=None):
    existing = db.session.query(Pitcher).filter_by(mlb_id=mlb_id).first()
    if existing:
        return existing
    row = Pitcher(mlb_id=mlb_id, full_name=f'P{mlb_id}', active=True, team_id=current_team)
    db.session.add(row)
    db.session.commit()
    return row


def _log(mlb_id, game_pk=GAME_PK, *, team, gs=0, outs=3, r=0, er=0, h=0, bb=0, k=0, hr=0,
         gdate=GDATE, game_type='R', status=GameLog.APPEARANCE_TEAM_RESOLVED,
         pitcher_row=None):
    row = pitcher_row or _pitcher(mlb_id)
    if status == GameLog.APPEARANCE_TEAM_RESOLVED:
        appearance_team_id, source, reason = team, 'boxscore_side', 'resolved_boxscore'
    else:
        appearance_team_id, source, reason = None, None, None
    log = GameLog(
        pitcher_id=row.id, mlb_game_pk=game_pk, game_date=gdate, game_type=game_type,
        games_started=gs, innings_pitched_outs=outs, innings_pitched=(outs / 3.0),
        runs_allowed=r, earned_runs=er, hits_allowed=h, walks=bb, strikeouts=k,
        home_runs_allowed=hr, appearance_team_status=status,
        appearance_team_id=appearance_team_id, appearance_team_source=source,
        appearance_team_reason=reason,
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


class _FakeMlbClient:
    def __init__(self, games=(), boxscores=None, raise_windows=(), raise_pks=()):
        self.games = list(games)
        self.boxscores = dict(boxscores or {})
        self.raise_windows = set(raise_windows)
        self.raise_pks = set(raise_pks)
        self.schedule_calls = []
        self.boxscore_calls = []

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        self.schedule_calls.append((start_date, end_date))
        if start_date in self.raise_windows:
            raise RuntimeError('schedule unavailable')
        return [g for g in self.games if start_date <= g['officialDate'] <= end_date]

    def get_game_boxscore(self, game_pk):
        self.boxscore_calls.append(game_pk)
        if game_pk in self.raise_pks:
            raise RuntimeError('boxscore unavailable')
        return self.boxscores.get(game_pk)


# One clean official game: A (home) starter 1 + relievers 2,3; B (away) starter 4 + 5,6.
_HOME_LINES = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
               _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
               _pline(3, gs=0, outs=3, r=0, er=0, k=1)]
_AWAY_LINES = [_pline(4, gs=1, outs=15, r=3, er=3, h=6, k=4),
               _pline(5, gs=0, outs=4, r=1, er=1, bb=1),
               _pline(6, gs=0, outs=2, r=0, er=0, hr=0)]


def _client(home_lines=None, away_lines=None, *, games=None, boxscores=None, **kwargs):
    if boxscores is None:
        boxscores = {GAME_PK: _boxscore(home_lines or _HOME_LINES, away_lines or _AWAY_LINES)}
    return _FakeMlbClient(games=games or [_official_game()], boxscores=boxscores, **kwargs)


def _seed_matching_local():
    """Local rows that exactly mirror the clean official game."""
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(3, team=A, gs=0, outs=3, r=0, er=0, k=1)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0, hr=0)


def _run(**kwargs):
    kwargs.setdefault('client', _client())
    return diag.run_diagnostic(**kwargs)


def _reasons(payload):
    return {reason for detail in payload['bounded_details'] for reason in detail['reason_codes']}


def _detail_for(payload, *, official_pitcher_id=None, local_pitcher_mlb_id=None):
    for detail in payload['bounded_details']:
        if official_pitcher_id is not None and detail['official_pitcher_id'] == official_pitcher_id:
            return detail
        if (local_pitcher_mlb_id is not None
                and detail['local_pitcher_mlb_id'] == local_pitcher_mlb_id
                and detail['official_pitcher_id'] is None):
            return detail
    raise AssertionError('detail not found')


# ═══════════════ 1. Exact complete team-game ════════════════════════════════
def test_exact_complete_team_game_passes(app):
    _seed_matching_local()
    payload = _run()
    assert payload['result'] == diag.RESULT_PASS
    assert payload['exit_code'] == 0
    assert payload['mode'] == 'read_only'
    assert payload['exact_match_count'] == 6
    assert payload['missing_local_line_count'] == 0
    assert payload['extra_local_line_count'] == 0
    assert payload['appearance_team_mismatch_count'] == 0
    assert payload['role_mismatch_count'] == 0
    assert payload['stat_mismatch_count'] == 0
    assert payload['decision_reasons'] == [
        'every_official_pitching_line_has_one_exact_local_counterpart']
    assert payload['database_writes_performed'] is False


def test_clean_game_reconciliations_hold(app):
    _seed_matching_local()
    payload = _run()
    recon = payload['reconciliations']
    assert payload['official_games_fetched'] == 1
    assert payload['official_team_game_sides'] == 2
    assert payload['expected_official_starter_lines'] == 2
    assert payload['official_starter_lines'] == 2
    assert payload['official_relief_lines'] == 4
    assert payload['official_pitching_lines'] == 6
    assert payload['local_pitching_lines'] == 6
    assert payload['local_starter_lines'] == 2
    assert payload['local_relief_lines'] == 4
    assert recon['official_games_times_two_equals_team_game_sides'] is True
    assert recon['every_team_game_side_has_unique_official_starter'] is True
    assert recon['official_starter_lines_equal_team_game_sides'] is True
    assert recon['official_starter_plus_relief_equals_pitching_lines'] is True
    assert recon['official_compared_lines_partition'] is True
    assert recon['local_lines_partition'] is True
    assert recon['classification_details_reconcile'] is True
    assert all(recon.values())


# ═══════════════ 2. Official reliever absent locally ════════════════════════
def test_official_reliever_absent_locally_fails(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['exit_code'] == 1
    assert payload['missing_local_line_count'] == 1
    assert payload['exact_match_count'] == 5
    assert diag.REASON_OFFICIAL_LINE_MISSING in payload['decision_reasons']
    detail = _detail_for(payload, official_pitcher_id=3)
    assert detail['reason_codes'] == [diag.REASON_OFFICIAL_LINE_MISSING]
    assert detail['official_role'] == diag.ROLE_RELIEF
    assert detail['team_id'] == A
    assert detail['local_pitcher_id'] is None
    # The absent line's official stats are reported, never zero-filled locally.
    assert detail['official_stats']['outs'] == 3
    assert detail['local_stats']['outs'] is None


# ═══════════════ 3. Official starter absent locally ═════════════════════════
def test_official_starter_absent_locally_fails(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(1).id).delete(synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['missing_local_line_count'] == 1
    detail = _detail_for(payload, official_pitcher_id=1)
    assert detail['official_role'] == diag.ROLE_STARTER
    assert detail['reason_codes'] == [diag.REASON_OFFICIAL_LINE_MISSING]
    assert payload['counts_by_team'][str(A)]['finding_count'] == 1


# ═══════════════ 4. Official pitcher absent from Pitcher ════════════════════
def test_official_pitcher_absent_from_pitcher_table(app):
    # Every local row exists except reliever 3, whose Pitcher identity is never created.
    _log(1, team=A, gs=1, outs=18, r=2, er=2, h=5, k=6)
    _log(2, team=A, gs=0, outs=3, r=1, er=1, h=1, k=2)
    _log(4, team=B, gs=1, outs=15, r=3, er=3, h=6, k=4)
    _log(5, team=B, gs=0, outs=4, r=1, er=1, bb=1)
    _log(6, team=B, gs=0, outs=2, r=0, er=0)
    assert db.session.query(Pitcher).filter_by(mlb_id=3).first() is None
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['missing_local_pitcher_identity_count'] == 1
    assert payload['missing_local_line_count'] == 1
    detail = _detail_for(payload, official_pitcher_id=3)
    assert detail['reason_codes'] == [diag.REASON_OFFICIAL_LINE_MISSING,
                                      diag.REASON_OFFICIAL_IDENTITY_MISSING]
    assert detail['official_pitcher_name'] == 'P3'


def test_identity_is_never_inferred_from_a_name(app):
    # A local row for a DIFFERENT MLB id but the SAME official name must not match.
    _seed_matching_local()
    stray = _pitcher(999)
    stray.full_name = 'P3'
    db.session.query(GameLog).filter(
        GameLog.pitcher_id == _pitcher(3).id).delete(synchronize_session=False)
    db.session.commit()
    _log(999, team=A, gs=0, outs=3, r=0, er=0, k=1, pitcher_row=stray)
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['missing_local_line_count'] == 1     # official line 3 still missing
    assert payload['extra_local_line_count'] == 1       # the name-alike row is extra
    assert _detail_for(payload, official_pitcher_id=3)['reason_codes'] == [
        diag.REASON_OFFICIAL_LINE_MISSING]
    assert _detail_for(payload, local_pitcher_mlb_id=999)['reason_codes'] == [
        diag.REASON_LOCAL_LINE_EXTRA]


# ═══════════════ 5. Local phantom line ══════════════════════════════════════
def test_local_phantom_line_not_in_official_section(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6, r=2, er=2)  # never appeared in the official box score
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['extra_local_line_count'] == 1
    assert payload['exact_match_count'] == 6
    assert diag.REASON_LOCAL_LINE_EXTRA in payload['decision_reasons']
    detail = _detail_for(payload, local_pitcher_mlb_id=77)
    assert detail['reason_codes'] == [diag.REASON_LOCAL_LINE_EXTRA]
    assert detail['official_pitcher_id'] is None
    assert detail['local_stats']['outs'] == 6
    assert payload['local_pitching_lines'] == 7


def test_local_pitcher_identity_missing_is_classified(app):
    # A local row whose stored identity carries no usable official MLB id (0 is not an id).
    _seed_matching_local()
    _log(0, team=A, gs=0, outs=3)
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['local_pitcher_identity_missing_count'] == 1
    assert payload['extra_local_line_count'] == 0   # unresolvable, never asserted as extra
    assert diag.REASON_LOCAL_IDENTITY_MISSING in payload['decision_reasons']


# ═══════════════ 6. Appearance-team mismatch ════════════════════════════════
def test_appearance_team_mismatch(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'appearance_team_id': B}, synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['appearance_team_mismatch_count'] == 1
    assert payload['exact_match_count'] == 5
    detail = _detail_for(payload, official_pitcher_id=2)
    assert detail['reason_codes'] == [diag.REASON_APPEARANCE_TEAM_MISMATCH]
    assert detail['team_id'] == A                      # official side
    assert detail['local_appearance_team_id'] == B     # local claim


def test_current_pitcher_team_is_never_authority(app):
    # A reliever whose CURRENT Pitcher.team_id is C still matches exactly: attribution is
    # decided by GameLog.appearance_team_id alone.
    _seed_matching_local()
    db.session.query(Pitcher).filter(Pitcher.mlb_id == 2).update(
        {'team_id': C}, synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_PASS
    assert payload['exact_match_count'] == 6
    assert str(C) not in payload['counts_by_team']


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


def test_service_never_reads_current_team_assignment():
    code = _code_without_prose(SERVICE_PATH)
    assert 'Pitcher.team_id' not in code
    assert 'team_abbreviation' not in code
    assert 'roster' not in code


# ═══════════════ 7. Starter/reliever classification mismatch ════════════════
def test_starter_relief_classification_mismatch(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'games_started': 1}, synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['role_mismatch_count'] == 1
    detail = _detail_for(payload, official_pitcher_id=2)
    assert detail['reason_codes'] == [diag.REASON_ROLE_MISMATCH]
    assert detail['official_role'] == diag.ROLE_RELIEF
    assert detail['local_games_started'] == 1


def test_null_local_games_started_is_never_read_as_zero(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        {'games_started': None}, synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['role_mismatch_count'] == 1
    detail = _detail_for(payload, official_pitcher_id=2)
    assert detail['local_games_started'] is None
    assert payload['local_unknown_role_lines'] == 1


# ═══════════════ 8. One-stat mismatch ═══════════════════════════════════════
@pytest.mark.parametrize('column,reason', [
    ('innings_pitched_outs', diag.REASON_OUTS_MISMATCH),
    ('runs_allowed', diag.REASON_RUNS_MISMATCH),
    ('earned_runs', diag.REASON_EARNED_RUNS_MISMATCH),
    ('hits_allowed', diag.REASON_HITS_MISMATCH),
    ('walks', diag.REASON_WALKS_MISMATCH),
    ('strikeouts', diag.REASON_STRIKEOUTS_MISMATCH),
    ('home_runs_allowed', diag.REASON_HOME_RUNS_MISMATCH),
])
def test_single_stat_mismatch_with_identical_identity(app, column, reason):
    _seed_matching_local()
    update = {column: 9}
    if column == 'innings_pitched_outs':
        update['innings_pitched'] = 3.0
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(2).id).update(
        update, synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['stat_mismatch_count'] == 1
    assert payload['exact_match_count'] == 5
    detail = _detail_for(payload, official_pitcher_id=2)
    assert detail['reason_codes'] == [reason]
    assert detail['local_pitcher_mlb_id'] == 2          # identity is otherwise identical
    assert detail['team_id'] == A


def test_null_local_stat_is_never_read_as_zero(app):
    _seed_matching_local()
    db.session.query(GameLog).filter(GameLog.pitcher_id == _pitcher(3).id).update(
        {'strikeouts': None}, synchronize_session=False)
    db.session.commit()
    payload = _run()
    assert payload['result'] == diag.RESULT_FAIL
    detail = _detail_for(payload, official_pitcher_id=3)
    assert detail['reason_codes'] == [diag.REASON_STRIKEOUTS_MISMATCH]
    assert detail['local_stats']['strikeouts'] is None


def test_missing_official_stat_is_evidence_gap_not_zero(app):
    _seed_matching_local()
    home = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
            _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2, drop=('homeRuns',)),
            _pline(3, gs=0, outs=3, r=0, er=0, k=1)]
    payload = diag.run_diagnostic(client=_client(home_lines=home))
    assert payload['result'] == diag.RESULT_INCONCLUSIVE
    assert payload['exit_code'] == 2
    detail = _detail_for(payload, official_pitcher_id=2)
    assert detail['reason_codes'] == [diag.REASON_OFFICIAL_EVIDENCE_UNAVAILABLE]
    assert detail['official_stats']['home_runs'] is None
    assert payload['stat_mismatch_count'] == 0


# ═══════════════ 9. Official starter missing ════════════════════════════════
def test_official_starter_missing_is_inconclusive(app):
    _seed_matching_local()
    home = [_pline(1, gs=0, outs=18, r=2, er=2, h=5, k=6),
            _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
            _pline(3, gs=0, outs=3, r=0, er=0, k=1)]
    payload = diag.run_diagnostic(client=_client(home_lines=home))
    assert payload['result'] == diag.RESULT_INCONCLUSIVE
    assert payload['exit_code'] == 2
    assert payload['decision_reasons'] == [diag.REASON_OFFICIAL_STARTER_MISSING]
    assert payload['official_sides_with_unique_starter'] == 1
    assert payload['official_starter_lines'] == 1
    assert payload['expected_official_starter_lines'] == 2
    recon = payload['reconciliations']
    assert recon['every_team_game_side_has_unique_official_starter'] is False
    assert recon['official_starter_lines_equal_team_game_sides'] is False
    # The uncompared side's local rows are neither matched nor called extra.
    assert payload['extra_local_line_count'] == 0
    assert payload['local_lines_not_evaluated'] == 3


def test_absent_official_games_started_is_not_read_as_relief(app):
    _seed_matching_local()
    home = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6, drop=('gamesStarted',)),
            _pline(2, gs=0, outs=3, r=1, er=1, h=1, k=2),
            _pline(3, gs=0, outs=3, r=0, er=0, k=1)]
    payload = diag.run_diagnostic(client=_client(home_lines=home))
    assert payload['result'] == diag.RESULT_INCONCLUSIVE
    assert diag.REASON_OFFICIAL_STARTER_MISSING in payload['counts_by_reason']


# ═══════════════ 10. Multiple official starters ═════════════════════════════
def test_multiple_official_starters_fails(app):
    _seed_matching_local()
    home = [_pline(1, gs=1, outs=18, r=2, er=2, h=5, k=6),
            _pline(2, gs=1, outs=3, r=1, er=1, h=1, k=2),
            _pline(3, gs=0, outs=3, r=0, er=0, k=1)]
    payload = diag.run_diagnostic(client=_client(home_lines=home))
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['exit_code'] == 1
    assert diag.REASON_OFFICIAL_STARTER_CONTRADICTORY in payload['decision_reasons']
    detail = [d for d in payload['bounded_details']
              if diag.REASON_OFFICIAL_STARTER_CONTRADICTORY in d['reason_codes']][0]
    assert detail['official_starter_count'] == 2
    assert detail['team_id'] == A


# ═══════════════ 11. Duplicate local line ═══════════════════════════════════
def test_duplicate_local_line_is_blocked_by_storage(app):
    # Two stored lines for one official identity in one game require two Pitcher rows with
    # the same mlb_id; the unique index makes that unreachable. The guard below classifies
    # the state anyway, so the diagnostic cannot silently accept a duplicate if it appears.
    _seed_matching_local()
    db.session.add(Pitcher(mlb_id=2, full_name='P2 duplicate', active=True))
    with pytest.raises(Exception):
        db.session.commit()
    db.session.rollback()
    assert db.session.query(Pitcher).filter_by(mlb_id=2).count() == 1


def test_duplicate_local_line_is_classified():
    # Identity-level duplicate classification, independent of storage constraints.
    class _Log:
        appearance_team_id = A
        games_started = 0
        innings_pitched_outs = 3
        runs_allowed = earned_runs = hits_allowed = walks = strikeouts = 0
        home_runs_allowed = 0

    line = diag._OfficialLine(
        game_pk=GAME_PK, game_date=GDATE, side='home', team_id=A, team_name='TeamA',
        pitcher_id=2, pitcher_name='P2', role=diag.ROLE_RELIEF,
        stats={'outs': 3, 'runs': 0, 'earned_runs': 0, 'hits': 0, 'walks': 0,
               'strikeouts': 0, 'home_runs': 0})
    matches = [diag._LocalLine(log=_Log(), pitcher_row_id=11, mlb_id=2),
               diag._LocalLine(log=_Log(), pitcher_row_id=12, mlb_id=2)]
    detail = diag._compare_official_line(line, matches)
    assert detail['reason_codes'] == [diag.REASON_LOCAL_DUPLICATE]


# ═══════════════ 12. Database remains unchanged ═════════════════════════════
def test_diagnostic_emits_no_write_sql(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6)          # force findings so every branch runs
    statements = []

    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        payload = _run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)
    writes = [st for st in statements
              if st.strip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
    assert writes == []
    assert payload['database_writes_performed'] is False


def test_source_rows_unchanged_after_run(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6)
    before = {row.id: (row.appearance_team_id, row.games_started, row.innings_pitched_outs,
                       row.earned_runs, row.strikeouts)
              for row in db.session.query(GameLog).all()}
    pitchers_before = {p.id: (p.mlb_id, p.team_id) for p in db.session.query(Pitcher).all()}
    _run()
    after = {row.id: (row.appearance_team_id, row.games_started, row.innings_pitched_outs,
                      row.earned_runs, row.strikeouts)
             for row in db.session.query(GameLog).all()}
    assert before == after
    assert pitchers_before == {p.id: (p.mlb_id, p.team_id)
                               for p in db.session.query(Pitcher).all()}


def test_service_contains_no_write_path():
    code = _code_without_prose(SERVICE_PATH)
    for token in ('session.add', 'session.commit', 'session.delete', 'session.merge',
                  'session.flush', 'session.bulk', 'INSERT INTO', 'DELETE FROM',
                  'UPDATE ', 'db.create_all', 'db.drop_all'):
        assert token not in code, token


# ═══════════════ 13. Determinism + detail bounding ══════════════════════════
def test_deterministic_output_across_runs(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6)
    first = _run()
    second = _run()
    assert first['bounded_details'] == second['bounded_details']
    assert first['counts_by_reason'] == second['counts_by_reason']
    assert first['counts_by_team'] == second['counts_by_team']


def test_details_sorted_by_game_team_then_identity(app):
    _seed_matching_local()
    payload = _run()
    keys = [(d['game_pk'], d['team_id'], d['official_pitcher_id'])
            for d in payload['bounded_details']]
    assert keys == sorted(keys)


def test_findings_sort_ahead_of_exact_matches(app):
    # A bounded window must surface defects, not the first game's clean lines.
    _seed_matching_local()
    _log(1, 9002, team=A, gs=1, outs=18)          # game 9002 line is extra: no official game
    client = _FakeMlbClient(
        games=[_official_game(), _official_game(9002)],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES),
                   9002: _boxscore([], [])})
    payload = diag.run_diagnostic(client=client, detail_limit=1)
    assert payload['detail_count'] > 1
    assert payload['bounded_details'][0]['reason_codes'] != [diag.REASON_EXACT_MATCH]


def test_detail_limit_bounds_output(app):
    _seed_matching_local()
    payload = _run(detail_limit=2)
    assert payload['detail_count'] == 6
    assert payload['bounded_detail_count'] == 2
    assert payload['details_truncated'] is True
    assert len(payload['bounded_details']) == 2
    # Bounding never changes the counts.
    assert payload['exact_match_count'] == 6


def test_detail_limit_is_clamped(app):
    _seed_matching_local()
    assert _run(detail_limit=99999)['inputs']['detail_limit'] == diag.MAX_DETAIL_LIMIT
    assert _run(detail_limit=-5)['inputs']['detail_limit'] == 0
    assert _run(detail_limit='nope')['inputs']['detail_limit'] == diag.DEFAULT_DETAIL_LIMIT


# ═══════════════ Scope, filters, and unavailable evidence ═══════════════════
def test_game_pk_filter_restricts_scope(app):
    _seed_matching_local()
    _log(1, 9002, team=A, gs=1, outs=18)
    client = _FakeMlbClient(
        games=[_official_game(), _official_game(9002)],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES),
                   9002: _boxscore(_HOME_LINES, _AWAY_LINES)})
    payload = diag.run_diagnostic(client=client, game_pk=GAME_PK)
    assert payload['official_games_selected'] == 1
    assert payload['inputs']['game_pk'] == GAME_PK
    assert payload['local_pitching_lines'] == 6


def test_team_id_filter_selects_that_teams_games_and_both_sides(app):
    _seed_matching_local()
    client = _FakeMlbClient(
        games=[_official_game(), _official_game(9002, home=C, away=400)],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES)})
    payload = diag.run_diagnostic(client=client, team_id=A)
    assert payload['official_games_selected'] == 1
    assert payload['official_team_game_sides'] == 2   # both sides still reconciled
    assert payload['result'] == diag.RESULT_PASS


def test_non_final_and_non_regular_official_games_are_out_of_scope(app):
    _seed_matching_local()
    client = _FakeMlbClient(
        games=[_official_game(), _official_game(9002, status_code='S'),
               _official_game(9003, game_type='S')],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES)})
    payload = diag.run_diagnostic(client=client)
    assert payload['official_games_selected'] == 1
    assert payload['result'] == diag.RESULT_PASS


def test_as_of_date_bounds_the_official_window(app):
    _seed_matching_local()
    client = _FakeMlbClient(
        games=[_official_game(), _official_game(9002, gdate=date(2026, 8, 1))],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES)})
    payload = diag.run_diagnostic(client=client, as_of_date=AS_OF)
    assert payload['official_games_selected'] == 1


def test_boxscore_fetch_failure_is_inconclusive(app):
    _seed_matching_local()
    payload = diag.run_diagnostic(client=_client(raise_pks=(GAME_PK,)))
    assert payload['result'] == diag.RESULT_INCONCLUSIVE
    assert payload['decision_reasons'] == [diag.REASON_OFFICIAL_EVIDENCE_UNAVAILABLE]
    assert payload['official_games_selected'] == 1
    assert payload['official_games_fetched'] == 0
    # An unfetched game can never prove a local line extra.
    assert payload['extra_local_line_count'] == 0
    assert payload['local_pitching_lines'] == 0


def test_schedule_failure_is_inconclusive(app):
    _seed_matching_local()
    payload = diag.run_diagnostic(client=_client(raise_windows=('2026-01-01',)))
    assert payload['result'] == diag.RESULT_INCONCLUSIVE
    assert diag.REASON_OFFICIAL_EVIDENCE_UNAVAILABLE in payload['decision_reasons']


def test_proven_defect_outranks_an_evidence_gap(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6)
    client = _FakeMlbClient(
        games=[_official_game(), _official_game(9002)],
        boxscores={GAME_PK: _boxscore(_HOME_LINES, _AWAY_LINES)},
        raise_pks=(9002,))
    payload = diag.run_diagnostic(client=client)
    assert payload['result'] == diag.RESULT_FAIL
    assert payload['decision_reasons'] == [diag.REASON_LOCAL_LINE_EXTRA]
    assert diag.REASON_OFFICIAL_EVIDENCE_UNAVAILABLE in payload['counts_by_reason']


def test_empty_official_population_is_inconclusive(app):
    payload = diag.run_diagnostic(client=_FakeMlbClient(games=[], boxscores={}))
    assert payload['result'] == diag.RESULT_INCONCLUSIVE
    assert payload['official_games_selected'] == 0


def test_non_regular_game_type_input_is_refused(app):
    with pytest.raises(ValueError):
        diag.run_diagnostic(game_type='P', client=_client())


# ═══════════════ Contract, vocabulary, and gates ════════════════════════════
def test_exit_code_map():
    assert diag.EXIT_BY_RESULT[diag.RESULT_PASS] == 0
    assert diag.EXIT_BY_RESULT[diag.RESULT_FAIL] == 1
    assert diag.EXIT_BY_RESULT[diag.RESULT_INCONCLUSIVE] == 2


def test_reason_vocabulary_is_complete_and_typed():
    vocabulary = {diag.REASON_EXACT_MATCH} | diag.FAIL_REASONS | diag.INCONCLUSIVE_REASONS
    assert vocabulary == {
        'exact_match',
        'official_line_missing_local_game_log',
        'local_line_not_in_official_pitching_section',
        'local_pitcher_identity_missing',
        'official_pitcher_identity_missing_from_pitcher_table',
        'appearance_team_mismatch',
        'starter_relief_classification_mismatch',
        'innings_outs_mismatch',
        'runs_mismatch',
        'earned_runs_mismatch',
        'hits_mismatch',
        'walks_mismatch',
        'strikeouts_mismatch',
        'home_runs_mismatch',
        'local_duplicate_line',
        'official_starter_missing',
        'official_starter_contradictory',
        'official_evidence_unavailable',
    }
    assert not (diag.FAIL_REASONS & diag.INCONCLUSIVE_REASONS)


def test_report_has_required_top_level_fields(app):
    _seed_matching_local()
    payload = _run()
    for key in ('result', 'exit_code', 'mode', 'season', 'as_of_date',
                'official_games_selected', 'official_games_fetched',
                'official_team_game_sides', 'expected_official_starter_lines',
                'official_pitching_lines', 'official_relief_lines', 'official_starter_lines',
                'local_pitching_lines', 'local_starter_lines', 'local_relief_lines',
                'exact_match_count', 'missing_local_line_count', 'extra_local_line_count',
                'missing_local_pitcher_identity_count', 'appearance_team_mismatch_count',
                'role_mismatch_count', 'stat_mismatch_count', 'counts_by_reason',
                'counts_by_team', 'bounded_details', 'reconciliations', 'decision_reasons',
                'database_writes_performed'):
        assert key in payload, key
    assert payload['season'] == SEASON
    assert payload['as_of_date'] == AS_OF.isoformat()
    assert payload['contracts']['diagnostic_contract_version'] == diag.DIAGNOSTIC_CONTRACT_VERSION


def test_every_detail_carries_the_full_key_set(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6)
    payload = _run()
    for detail in payload['bounded_details']:
        assert set(detail) == set(diag.DETAIL_KEYS)
        assert detail['reason_codes']


def test_gates_remain_blocked(app):
    _seed_matching_local()
    payload = _run()
    assert payload['result'] == diag.RESULT_PASS
    assert payload['repair_status'] == 'not_implemented_in_this_branch'
    assert payload['foundation_3b_gate'] == 'blocked'
    assert payload['public_reader_gate'] == 'blocked'
    assert payload['share_card_performance_gate'] == 'blocked'


def test_report_contains_no_secret_or_raw_payload(app):
    _seed_matching_local()
    blob = str(_run()).lower()
    for token in ('password', 'secret', 'postgres://', 'database_url', 'statuscode',
                  'abstractgamestate'):
        assert token not in blob


def test_counts_by_team_are_keyed_and_sorted(app):
    _seed_matching_local()
    _log(77, team=A, gs=0, outs=6)
    payload = _run()
    assert list(payload['counts_by_team']) == sorted(payload['counts_by_team'])
    assert payload['counts_by_team'][str(A)]['official_pitching_lines'] == 3
    assert payload['counts_by_team'][str(A)]['local_pitching_lines'] == 4
    assert payload['counts_by_team'][str(A)]['exact_match'] == 3
    assert payload['counts_by_team'][str(A)]['finding_count'] == 1
    assert payload['counts_by_team'][str(B)]['finding_count'] == 0


def test_starter_identity_uses_only_games_started():
    src = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'ordered[0]' not in src      # no first-pitcher fallback
    assert 'pitchers[0]' not in src


# ═══════════════ CLI + workflow ═════════════════════════════════════════════
def test_cli_helpers_and_defaults():
    import argparse
    from scripts import run_official_pitching_line_completeness_2026 as cli
    assert cli.CAPABILITY == diag.CAPABILITY
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
    assert parsed.detail_limit == 100
    assert parsed.team_id is None and parsed.game_pk is None


def test_cli_sets_auto_sync_off_and_has_no_repair_flag():
    src = CLI_PATH.read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in src
    for token in ('--apply', '--repair', '--backfill', '--fix'):
        assert token not in src


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
    assert 'run_official_pitching_line_completeness_2026.py' in src
    assert "payload.get('database_writes_performed')" in src
    assert "raise SystemExit('Diagnostic must not perform database writes.')" in src
    for token in ('--apply', '--repair', 'confirmation:', 'expected_fingerprint'):
        assert token not in src


def test_workflow_rejects_a_write_or_non_read_only_payload():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert "if payload.get('database_writes_performed') is not False:" in src
    assert "raise SystemExit('Diagnostic must not perform database writes.')" in src
    assert "if payload.get('mode') != 'read_only':" in src
    assert "raise SystemExit('Diagnostic must run in read_only mode.')" in src


def _workflow_without_comments():
    """Workflow source with comment lines removed, so prose cannot satisfy a guard."""
    return '\n'.join(
        line for line in WORKFLOW_PATH.read_text(encoding='utf-8').splitlines()
        if not line.strip().startswith('#')
    )


def test_workflow_introduces_no_repair_or_automatic_execution():
    src = _workflow_without_comments()
    for token in ('--apply', '--repair', '--backfill', '--fix', 'backfill',
                  'reconcile', 'autofix', 'cron:', 'schedule:'):
        assert token not in src, token
    # The only gate values the workflow reports are the blocked ones it reads back.
    for gate in ("payload.get('foundation_3b_gate')", "payload.get('public_reader_gate')",
                 "payload.get('share_card_performance_gate')"):
        assert gate in src


# ── Production bootstrap configuration ────────────────────────────────────────
def _workflow_lines():
    return WORKFLOW_PATH.read_text(encoding='utf-8').splitlines()


def _validation_step_block():
    """The body of the 'Validate diagnostic inputs' step."""
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    start = src.index('- name: Validate diagnostic inputs')
    end = src.index('- name: Run read-only completeness diagnostic')
    return src[start:end]


def test_workflow_job_environment_sources_every_production_secret():
    lines = _workflow_lines()
    # Job-level env, six-space indented under jobs.diagnose.env.
    for entry in ('      APP_ENV: production',
                  "      AUTO_SYNC: 'false'",
                  '      FLASK_APP: app.py',
                  '      DATABASE_URL: ${{ secrets.DATABASE_URL }}',
                  '      SECRET_KEY: ${{ secrets.SECRET_KEY }}',
                  '      ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'):
        assert entry in lines, entry


def test_admin_api_token_is_available_to_the_validation_step():
    block = _validation_step_block()
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in block


def test_validation_requires_all_three_production_secrets():
    block = _validation_step_block()
    for guard in ('[ -z "${DATABASE_URL:-}" ]',
                  '[ -z "${SECRET_KEY:-}" ]',
                  '[ -z "${ADMIN_API_TOKEN:-}" ]'):
        assert guard in block, guard
    assert 'echo "::error::Missing required production repository secret."' in block


def test_workflow_never_prints_a_secret_value_or_length():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    for leak in ('${#ADMIN_API_TOKEN}', '${#SECRET_KEY}', '${#DATABASE_URL}',
                 'echo "$ADMIN_API_TOKEN"', 'echo "$SECRET_KEY"', 'echo "$DATABASE_URL"',
                 'echo $ADMIN_API_TOKEN', 'echo $SECRET_KEY', 'echo $DATABASE_URL'):
        assert leak not in src, leak
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('echo'):
            for name in ('ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL'):
                assert name not in stripped, stripped


def test_workflow_inputs_match_the_cli():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    for name in ('season:', 'as_of_date:', 'detail_limit:', 'team_id:', 'game_pk:'):
        assert name in src
    for flag in ('--season', '--as-of-date', '--detail-limit', '--team-id', '--game-pk'):
        assert flag in src


def test_workflow_summary_uses_real_fields():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    for field in ("payload.get('result')", "payload.get('official_games_fetched')",
                  "payload.get('official_team_game_sides')",
                  "payload.get('expected_official_starter_lines')",
                  "payload.get('exact_match_count')",
                  "payload.get('missing_local_line_count')",
                  "payload.get('extra_local_line_count')",
                  "payload.get('appearance_team_mismatch_count')",
                  "payload.get('role_mismatch_count')",
                  "payload.get('stat_mismatch_count')"):
        assert field in src


def test_decision_record_exists():
    record = (REPO_ROOT / 'docs' / 'decisions'
              / '2026-07-27-official-pitching-line-completeness-diagnostic.md')
    text = record.read_text(encoding='utf-8')
    assert 'complete_team_games' in text
    assert 'read-only' in text.lower()
