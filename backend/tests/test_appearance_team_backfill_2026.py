"""Foundation 2 — governed 2026 historical team-at-appearance backfill.

Exercises the backfill contract end to end against the REAL Foundation 1 resolver and
box-score parser (no test doubles for resolution): deterministic keyset target
selection (2026 window, legacy-NULL only, final games only); local-evidence-first
resolution (Tier 1 schedule via CompletedGameContext; Tier 2 one box-score call); the
read-only plan + plan-binding fingerprint; the MANDATORY apply confirmation +
fingerprint gates; per-game atomic isolation with stop-at-failure cursor semantics;
strict PASS/FAIL/INCONCLUSIVE classification and exit codes; idempotent re-runs; the
stored-state invariant; the before/after coverage audit; report reconciliation; and
the guarantees that no second resolver is invented and the pitcher's current team is
never consulted.
"""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.completed_game_context import CompletedGameContext
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority as ata
from services import appearance_team_backfill_2026 as backfill
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


TEAM_A, TEAM_B, TEAM_C, TEAM_D = 111, 222, 333, 444
IN_WINDOW = date(2026, 6, 20)
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'appearance_team_backfill_2026.py'
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'appearance_team_backfill_2026.yml'
PHRASE = backfill.CONFIRMATION_PHRASE


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


# ── Fixtures ──────────────────────────────────────────────────────────────────
def _pitcher(mlb_id, current_team_id=None):
    pitcher = Pitcher(mlb_id=mlb_id, full_name=f'P{mlb_id}', team_id=current_team_id,
                      active=True)
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _schedule(game_pk, home, away, game_date=IN_WINDOW, home_state='final', away_state='final'):
    db.session.add_all([
        ScheduledGame(team_id=home, game_pk=game_pk, game_date=game_date,
                      status_state=home_state, home_away='home', opponent_team_id=away),
        ScheduledGame(team_id=away, game_pk=game_pk, game_date=game_date,
                      status_state=away_state, home_away='away', opponent_team_id=home),
    ])
    db.session.commit()


def _context(game_pk, team_id, opponent_team_id, opponent_name, game_date=IN_WINDOW,
             starter_player_id=None):
    db.session.add(CompletedGameContext(
        team_id=team_id, game_pk=game_pk, game_date=game_date,
        opponent_team_id=opponent_team_id, opponent_name=opponent_name,
        starter_player_id=starter_player_id,
    ))
    db.session.commit()


def _log(pitcher_id, game_pk, game_date=IN_WINDOW, opponent='TeamB', opponent_abbr='TB',
         outs=3, status=None, team_id=None, source=None, reason=None):
    log = GameLog(
        pitcher_id=pitcher_id, mlb_game_pk=game_pk, game_date=game_date,
        opponent=opponent, opponent_abbreviation=opponent_abbr, game_type='R',
        innings_pitched=outs / 3.0, innings_pitched_outs=outs,
        appearance_team_status=status, appearance_team_id=team_id,
        appearance_team_source=source, appearance_team_reason=reason,
    )
    db.session.add(log)
    db.session.commit()
    return log


def _pitline(pid, ip='1.0', er=0, gs=None):
    stats = {'inningsPitched': ip, 'earnedRuns': str(er), 'runs': str(er), 'hits': '0',
             'baseOnBalls': '0', 'strikeOuts': '1', 'homeRuns': '0',
             'numberOfPitches': '12', 'strikes': '8'}
    if gs is not None:
        stats['gamesStarted'] = str(gs)
    return {'person': {'id': pid, 'fullName': f'P{pid}'}, 'stats': {'pitching': stats}}


def _boxscore(home_team, away_team, home_pids=(), away_pids=()):
    def _side(team_id, pids):
        return {'team': {'id': team_id, 'name': f'Team{team_id}'},
                'pitchers': list(pids),
                'players': {f'ID{pid}': _pitline(pid) for pid in pids}}
    return {'teams': {'home': _side(home_team, home_pids),
                      'away': _side(away_team, away_pids)}}


class _FakeClient:
    def __init__(self, boxscores=None, raise_for=()):
        self.boxscores = dict(boxscores or {})
        self.raise_for = set(raise_for)
        self.calls = []

    def get_game_boxscore(self, game_pk):
        self.calls.append(game_pk)
        if game_pk in self.raise_for:
            raise RuntimeError('boxscore unavailable')
        return self.boxscores[game_pk]


def _reload(log):
    return db.session.get(GameLog, log.id)


def _log_only(pitcher_id, game_pk):
    return (
        db.session.query(GameLog)
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.mlb_game_pk == game_pk)
        .one()
    )


def _run(**kwargs):
    kwargs.setdefault('client', _FakeClient())
    kwargs.setdefault('start_date', date(2026, 1, 1))
    kwargs.setdefault('end_date', date(2026, 12, 31))
    return backfill.run_backfill(**kwargs)


def _apply(*, client=None, **kwargs):
    """Mandatory-fingerprint apply: dry-run for the approved fingerprint, then apply
    with the SAME client so the plan is identical."""
    client = client or _FakeClient()
    plan = _run(client=client, **kwargs)
    return _run(client=client, apply=True, confirmation=PHRASE,
                expected_fingerprint=plan['batch_fingerprint'], **kwargs)


# ═══════════════════════════ A. Target selection ════════════════════════════
def test_selects_legacy_null_row_in_window(app):
    p = _pitcher(9001)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    assert _run(allow_api=False)['games_selected'] == 1


def test_excludes_row_before_window(app):
    p = _pitcher(9002)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2025, 9, 1))
    _log(p.id, 700, game_date=date(2025, 9, 1))
    assert _run(allow_api=False, start_date=date(2026, 1, 1))['games_selected'] == 0


def test_excludes_row_after_window(app):
    p = _pitcher(9003)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2027, 4, 1))
    _log(p.id, 700, game_date=date(2027, 4, 1))
    assert _run(allow_api=False, end_date=date(2026, 12, 31))['games_selected'] == 0


def test_excludes_already_resolved_row(app):
    p = _pitcher(9004)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, status=ata.STATUS_RESOLVED, team_id=TEAM_A,
         source=ata.SOURCE_BOXSCORE, reason=ata.REASON_RESOLVED_BOXSCORE)
    assert _run(allow_api=False)['games_selected'] == 0


def test_excludes_already_unresolved_row(app):
    p = _pitcher(9005)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, status=ata.STATUS_UNRESOLVED, reason=ata.REASON_UNRESOLVED)
    assert _run(allow_api=False)['games_selected'] == 0


def test_excludes_already_conflict_row(app):
    p = _pitcher(9006)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, status=ata.STATUS_CONFLICT, source=ata.SOURCE_CONFLICT,
         reason=ata.REASON_CONFLICT)
    assert _run(allow_api=False)['games_selected'] == 0


def test_excludes_scheduled_not_final_game(app):
    p = _pitcher(9007)
    _schedule(700, TEAM_A, TEAM_B, home_state='scheduled', away_state='scheduled')
    _log(p.id, 700)
    assert _run(allow_api=False)['games_selected'] == 0


def test_excludes_suspended_game(app):
    p = _pitcher(9008)
    _schedule(700, TEAM_A, TEAM_B, home_state='final', away_state='suspended')
    _log(p.id, 700)
    assert _run(allow_api=False)['games_selected'] == 0


def test_excludes_postponed_game(app):
    p = _pitcher(9009)
    _schedule(700, TEAM_A, TEAM_B, home_state='postponed', away_state='postponed')
    _log(p.id, 700)
    assert _run(allow_api=False)['games_selected'] == 0


def test_excludes_game_with_no_schedule_evidence(app):
    p = _pitcher(9010)
    _log(p.id, 700)  # no ScheduledGame -> fail closed, not selected
    assert _run(allow_api=False)['games_selected'] == 0


def test_two_appearances_one_game_is_one_selected_two_targets(app):
    p1, p2 = _pitcher(9011), _pitcher(9012)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p1.id, 700)
    _log(p2.id, 700)
    summary = _run(allow_api=False)
    assert summary['games_selected'] == 1
    assert summary['appearances_targeted'] == 2


def test_keyset_cursor_excludes_past_games(app):
    p = _pitcher(9013)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _log(p.id, 700, game_date=date(2026, 4, 1))
    _log(p.id, 701, game_date=date(2026, 4, 2))
    summary = _run(allow_api=False, after_game_date=date(2026, 4, 1), after_game_pk=700)
    assert summary['games_selected'] == 1


def test_ordering_game_date_then_game_pk(app):
    p = _pitcher(9014)
    _schedule(702, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    for pk, d in ((702, date(2026, 4, 2)), (701, date(2026, 4, 1)), (700, date(2026, 4, 1))):
        _log(p.id, pk, game_date=d)
    summary = _run(allow_api=False, batch_size=1)
    assert summary['next_cursor'] == {'after_game_date': '2026-04-01', 'after_game_pk': 700}


def test_batch_size_limits_distinct_games(app):
    p = _pitcher(9015)
    for i, pk in enumerate((700, 701, 702)):
        _schedule(pk, TEAM_A, TEAM_B, game_date=date(2026, 4, 1 + i))
        _log(p.id, pk, game_date=date(2026, 4, 1 + i))
    summary = _run(allow_api=False, batch_size=2)
    assert summary['games_selected'] == 2
    assert summary['has_more'] is True


def test_batch_size_is_clamped(app):
    assert backfill._clamp_batch_size(10 ** 9) == backfill.MAX_BATCH_SIZE
    assert backfill._clamp_batch_size(0) == 1
    assert backfill._clamp_batch_size('nan') == backfill.DEFAULT_BATCH_SIZE


def test_no_offset_pagination_in_source(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert '.offset(' not in source
    assert 'keyset' in source.lower()


def test_cursor_tiebreak_within_same_date(app):
    p = _pitcher(9018)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _log(p.id, 700, game_date=date(2026, 4, 1))
    _log(p.id, 701, game_date=date(2026, 4, 1))
    summary = _run(allow_api=False, after_game_date=date(2026, 4, 1), after_game_pk=700)
    assert summary['games_selected'] == 1


# ═══════════════════ B. Tier 1 local resolution (no API) ════════════════════
def test_tier1_resolves_via_context_opponent_name(app):
    p = _pitcher(9101)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'Rivals')
    _log(p.id, 700, opponent='Rivals')
    client = _FakeClient()
    _apply(client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_RESOLVED
    assert row.appearance_team_id == TEAM_A
    assert row.appearance_team_source == ata.SOURCE_SCHEDULE
    assert client.calls == []


def test_tier1_resolves_via_starter_identity(app):
    p = _pitcher(9102)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'Someone', starter_player_id=9102)
    _log(p.id, 700, opponent='UnmatchedName')
    client = _FakeClient()
    _apply(client=client)
    assert _reload(_log_only(p.id, 700)).appearance_team_id == TEAM_A
    assert client.calls == []


def test_tier1_makes_no_api_call(app):
    p = _pitcher(9103)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient()
    _run(client=client)
    assert client.calls == []


def test_tier1_ambiguous_name_falls_to_api(app):
    p = _pitcher(9104)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'DifferentName')
    _log(p.id, 700, opponent='NoSuchTeam')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9104])})
    _run(client=client)
    assert client.calls == [700]


def test_tier1_name_match_resolves_correct_facing_team(app):
    p = _pitcher(9106)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_B, TEAM_A, 'Aces')  # B faced A ('Aces')
    _log(p.id, 700, opponent='Aces')
    _apply()
    assert _reload(_log_only(p.id, 700)).appearance_team_id == TEAM_B


def test_tier1_schedule_ambiguous_falls_to_api(app):
    p = _pitcher(9107)
    db.session.add_all([
        ScheduledGame(team_id=TEAM_A, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='home', opponent_team_id=TEAM_B),
        ScheduledGame(team_id=TEAM_C, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='away', opponent_team_id=TEAM_B),
    ])
    db.session.commit()
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9107])})
    _run(client=client)
    assert client.calls == [700]


# ═══════════════════ C. Tier 2 box-score resolution ═════════════════════════
def test_tier2_resolves_via_boxscore(app):
    p = _pitcher(9201)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9201])})
    _apply(client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_RESOLVED
    assert row.appearance_team_id == TEAM_A
    assert row.appearance_team_source == ata.SOURCE_BOXSCORE


def test_tier2_exactly_one_call_per_game(app):
    p1, p2 = _pitcher(9202), _pitcher(9203)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p1.id, 700)
    _log(p2.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9202, 9203])})
    _run(client=client)  # single dry run: one fetch per game
    assert client.calls == [700]


def test_tier2_resolves_each_pitcher_to_own_side(app):
    home_p, away_p = _pitcher(9204), _pitcher(9205)
    _schedule(700, TEAM_A, TEAM_B)
    _log(home_p.id, 700, opponent='TeamB')
    _log(away_p.id, 700, opponent='TeamA')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9204], away_pids=[9205])})
    _apply(client=client)
    assert _reload(_log_only(home_p.id, 700)).appearance_team_id == TEAM_A
    assert _reload(_log_only(away_p.id, 700)).appearance_team_id == TEAM_B


def test_tier2_boxscore_schedule_conflict_clears_team(app):
    p = _pitcher(9206)
    db.session.add_all([
        ScheduledGame(team_id=TEAM_C, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='home', opponent_team_id=TEAM_B),
        ScheduledGame(team_id=TEAM_B, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='away', opponent_team_id=TEAM_C),
    ])
    db.session.commit()
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9206])})
    _apply(client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_CONFLICT
    assert row.appearance_team_id is None


def test_tier2_no_matching_line_is_unresolved(app):
    p = _pitcher(9207)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[999999])})
    _apply(client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_UNRESOLVED
    assert row.appearance_team_id is None


def test_no_api_flag_leaves_unresolved(app):
    p = _pitcher(9212)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9212])})
    _apply(client=client, allow_api=False)
    assert client.calls == []
    assert _reload(_log_only(p.id, 700)).appearance_team_status == ata.STATUS_UNRESOLVED


# ═══════════════════════ D. Dry-run read-only ═══════════════════════════════
def test_dry_run_writes_nothing(app):
    p = _pitcher(9301)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9301])})
    summary = _run(client=client)
    assert summary['mode'] == 'dry_run'
    assert summary['database_writes_performed'] is False
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_dry_run_reports_proposed_counts(app):
    p = _pitcher(9302)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run()
    assert summary['proposed_resolved'] == 1


def test_dry_run_emits_no_write_sql(app):
    p = _pitcher(9304)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    statements = []

    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        _run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)
    writes = [s for s in statements
              if s.strip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
    assert writes == []


def test_dry_run_preserves_seed_rows(app):
    p = _pitcher(9306)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    _run(allow_api=False)
    assert db.session.query(GameLog).count() == 1
    assert db.session.query(ScheduledGame).count() == 2


# ═══════════════ E. Apply + MANDATORY fingerprint gates ═════════════════════
def test_apply_without_confirmation_refused(app):
    p = _pitcher(9401)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    fp = _run()['batch_fingerprint']
    summary = _run(apply=True, expected_fingerprint=fp)
    assert summary['result'] == backfill.RESULT_REFUSED
    assert summary['decision_reasons'] == ['confirmation_phrase_required']
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_apply_without_fingerprint_refused(app):
    p = _pitcher(9420)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run(apply=True, confirmation=PHRASE)  # no expected_fingerprint
    assert summary['result'] == backfill.RESULT_REFUSED
    assert summary['decision_reasons'] == ['approved_fingerprint_required']
    assert summary['database_writes_performed'] is False
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_apply_with_confirmation_and_fingerprint_writes(app):
    p = _pitcher(9403)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _apply()
    assert summary['result'] == backfill.RESULT_PASS
    assert summary['database_writes_performed'] is True
    assert _reload(_log_only(p.id, 700)).appearance_team_status == ata.STATUS_RESOLVED


def test_apply_with_mismatched_fingerprint_refused(app):
    p = _pitcher(9405)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run(apply=True, confirmation=PHRASE, expected_fingerprint='deadbeef')
    assert summary['result'] == backfill.RESULT_REFUSED
    assert summary['decision_reasons'] == ['fingerprint_mismatch']
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_apply_persists_resolved_provenance(app):
    p = _pitcher(9407)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _apply()
    row = _reload(_log_only(p.id, 700))
    assert (row.appearance_team_id, row.appearance_team_source, row.appearance_team_reason) == (
        TEAM_A, ata.SOURCE_SCHEDULE, ata.REASON_RESOLVED_SCHEDULE,
    )


def test_apply_persists_conflict(app):
    p = _pitcher(9409)
    db.session.add_all([
        ScheduledGame(team_id=TEAM_C, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='home', opponent_team_id=TEAM_B),
        ScheduledGame(team_id=TEAM_B, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='away', opponent_team_id=TEAM_C),
    ])
    db.session.commit()
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9409])})
    _apply(client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_CONFLICT
    assert row.appearance_team_source == ata.SOURCE_CONFLICT


# ═══════════════ F. Fingerprint binds the resolution plan ═══════════════════
def test_fingerprint_stable_across_dry_runs(app):
    p = _pitcher(9501)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    assert _run()['batch_fingerprint'] == _run()['batch_fingerprint']


def test_fingerprint_changes_when_target_set_changes(app):
    p = _pitcher(9502)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    first = _run()['batch_fingerprint']
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 3))
    _context(701, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 3))
    _log(p.id, 701, game_date=date(2026, 4, 3), opponent='TeamB')
    assert _run()['batch_fingerprint'] != first


def test_fingerprint_changes_with_cursor(app):
    p = _pitcher(9503)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _context(701, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 2))
    _log(p.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(p.id, 701, game_date=date(2026, 4, 2), opponent='TeamB')
    base = _run()['batch_fingerprint']
    moved = _run(after_game_date=date(2026, 4, 1), after_game_pk=700)['batch_fingerprint']
    assert base != moved


def test_fingerprint_depends_on_resolver_contract_version(monkeypatch, app):
    p = _pitcher(9504)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    base = _run()['batch_fingerprint']
    monkeypatch.setattr(backfill, 'RESOLVER_CONTRACT_VERSION', 'changed_contract_vX')
    assert _run()['batch_fingerprint'] != base


def test_fingerprint_changes_when_boxscore_evidence_changes(app):
    # Same target row IDs, different official attribution -> different fingerprint.
    p = _pitcher(9505)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    on_home = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9505])})
    on_away = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, away_pids=[9505])})
    fp_home = _run(client=on_home)['batch_fingerprint']
    fp_away = _run(client=on_away)['batch_fingerprint']
    assert fp_home != fp_away


def test_apply_with_stale_fingerprint_after_evidence_change_refused(app):
    p = _pitcher(9506)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9506])})
    stale_fp = _run(client=client)['batch_fingerprint']
    client.boxscores[700] = _boxscore(TEAM_A, TEAM_B, away_pids=[9506])  # evidence moved
    summary = _run(client=client, apply=True, confirmation=PHRASE,
                   expected_fingerprint=stale_fp)
    assert summary['result'] == backfill.RESULT_REFUSED
    assert summary['decision_reasons'] == ['fingerprint_mismatch']
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_added_target_row_invalidates_fingerprint(app):
    p1 = _pitcher(9510)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p1.id, 700, opponent='TeamB')
    approved = _run()['batch_fingerprint']
    p2 = _pitcher(9511)
    _log(p2.id, 700, opponent='TeamB')  # concurrent new target row in the same game
    summary = _run(apply=True, confirmation=PHRASE, expected_fingerprint=approved)
    assert summary['result'] == backfill.RESULT_REFUSED
    assert _reload(_log_only(p1.id, 700)).appearance_team_status is None


# ═══════════════════════ G. Idempotency / re-run ════════════════════════════
def test_rerun_after_apply_is_noop(app):
    p = _pitcher(9601)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _apply()
    second = _run()
    assert second['games_selected'] == 0
    assert second['result'] == backfill.RESULT_INCONCLUSIVE


def test_double_apply_is_idempotent(app):
    p = _pitcher(9602)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _apply()
    before = _reload(_log_only(p.id, 700)).appearance_team_id
    second = _run(apply=True, confirmation=PHRASE,
                  expected_fingerprint=_run()['batch_fingerprint'])
    assert _reload(_log_only(p.id, 700)).appearance_team_id == before
    assert second['result'] == backfill.RESULT_INCONCLUSIVE


# ═══════════════ H. Invariant / stored-state safety ═════════════════════════
def test_apply_keeps_invalid_stored_states_zero(app):
    p1, p2 = _pitcher(9701), _pitcher(9702)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p1.id, 700, opponent='TeamB')
    _log(p2.id, 700, opponent='TeamB')
    summary = _apply()
    assert summary['coverage_after']['invalid_stored_states'] == 0


def test_nonresolved_rows_have_no_team(app):
    p = _pitcher(9704)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[123])})
    _apply(client=client)
    assert _reload(_log_only(p.id, 700)).appearance_team_id is None


def test_never_overwrites_explicit_unresolved_alongside_targets(app):
    explicit, target = _pitcher(9705), _pitcher(9706)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(explicit.id, 700, opponent='TeamB', status=ata.STATUS_UNRESOLVED,
         reason=ata.REASON_UNRESOLVED)
    _log(target.id, 700, opponent='TeamB')
    _apply()
    assert _reload(_log_only(explicit.id, 700)).appearance_team_status == ata.STATUS_UNRESOLVED
    assert _reload(_log_only(target.id, 700)).appearance_team_status == ata.STATUS_RESOLVED


# ═══════════════ I. Reuse / never current team ══════════════════════════════
def test_service_source_never_references_pitcher_team_id(app):
    lowered = SERVICE_PATH.read_text(encoding='utf-8').lower()
    assert 'pitcher.team_id' not in lowered
    assert 'Pitcher.mlb_id' in SERVICE_PATH.read_text(encoding='utf-8')


def test_service_reuses_foundation1_parser_and_seam(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'sync_service._extract_pitching_lines_from_boxscore' in source
    assert 'sync_service._appearance_team_for_boxscore_line' in source


def test_service_defines_no_second_resolver(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'ata.resolve_for_write' in source
    assert 'def resolve_for_write' not in source
    assert 'def resolve_from_schedule' not in source


def test_attribution_ignores_current_team_traded_pitcher(app):
    p = _pitcher(9708, current_team_id=TEAM_C)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _apply()
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_id == TEAM_A
    assert row.appearance_team_id != p.team_id


# ═══════════════════ J. Coverage audit before/after ═════════════════════════
def test_summary_includes_before_and_after_coverage(app):
    p = _pitcher(9801)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run(allow_api=False)
    assert 'coverage_before' in summary and 'coverage_after' in summary


def test_apply_reduces_season_null_legacy(app):
    p = _pitcher(9802)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _apply()
    assert summary['coverage_before']['season_null_legacy'] == 1
    assert summary['coverage_after']['season_null_legacy'] == 0


def test_campaign_goal_full_apply_zeroes_2026_null_legacy(app):
    p1, p2 = _pitcher(9804), _pitcher(9805)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _context(701, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 2))
    _log(p1.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(p2.id, 701, game_date=date(2026, 4, 2), opponent='TeamB')
    summary = _apply()
    assert summary['coverage_after']['season_null_legacy'] == 0


# ═══════════════ K. Failure / cursor / result (Gates 3 & 4) ═════════════════
def test_clean_batch_pass(app):
    p = _pitcher(9550)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run()
    assert summary['result'] == backfill.RESULT_PASS
    assert summary['exit_code'] == 0


def test_no_targets_inconclusive(app):
    summary = _run()
    assert summary['result'] == backfill.RESULT_INCONCLUSIVE
    assert summary['exit_code'] == 2


def test_confirmation_mismatch_refused_exit1(app):
    p = _pitcher(9560)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    fp = _run()['batch_fingerprint']
    summary = _run(apply=True, confirmation='wrong', expected_fingerprint=fp)
    assert summary['result'] == backfill.RESULT_REFUSED
    assert summary['exit_code'] == 1
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_middle_game_api_failure_returns_fail_and_stops_cursor(app):
    a, b, c = _pitcher(9520), _pitcher(9521), _pitcher(9522)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _schedule(702, TEAM_A, TEAM_B, game_date=date(2026, 4, 3))
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _log(a.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')  # Tier 1, no API
    _log(b.id, 701, game_date=date(2026, 4, 2))                    # needs API -> fails
    _log(c.id, 702, game_date=date(2026, 4, 3))
    client = _FakeClient(raise_for=[701])
    plan = _run(client=client)
    assert plan['result'] == backfill.RESULT_FAIL
    assert plan['games_planned'] == 1
    summary = _run(client=client, apply=True, confirmation=PHRASE,
                   expected_fingerprint=plan['batch_fingerprint'])
    assert summary['result'] == backfill.RESULT_FAIL
    assert summary['exit_code'] == 1
    assert summary['decision_reasons'] == ['game_resolution_failure']
    assert _reload(_log_only(a.id, 700)).appearance_team_status == ata.STATUS_RESOLVED
    assert _reload(_log_only(b.id, 701)).appearance_team_status is None
    assert _reload(_log_only(c.id, 702)).appearance_team_status is None
    assert summary['next_cursor'] == {'after_game_date': '2026-04-01', 'after_game_pk': 700}


def test_retry_after_recovery_processes_failed_game(app):
    a, b = _pitcher(9524), _pitcher(9525)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _log(a.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(b.id, 701, game_date=date(2026, 4, 2))
    client = _FakeClient(raise_for=[701])
    plan1 = _run(client=client)
    run1 = _run(client=client, apply=True, confirmation=PHRASE,
                expected_fingerprint=plan1['batch_fingerprint'])
    assert _reload(_log_only(a.id, 700)).appearance_team_status == ata.STATUS_RESOLVED
    assert _reload(_log_only(b.id, 701)).appearance_team_status is None
    # Recover the API and resume from the cursor.
    client.raise_for.discard(701)
    client.boxscores[701] = _boxscore(TEAM_A, TEAM_B, home_pids=[9525])
    cur = run1['next_cursor']
    resume_kwargs = dict(after_game_date=date.fromisoformat(cur['after_game_date']),
                         after_game_pk=cur['after_game_pk'])
    plan2 = _run(client=client, **resume_kwargs)
    _run(client=client, apply=True, confirmation=PHRASE,
         expected_fingerprint=plan2['batch_fingerprint'], **resume_kwargs)
    assert _reload(_log_only(b.id, 701)).appearance_team_status == ata.STATUS_RESOLVED


def test_commit_failure_rolls_back_game(monkeypatch, app):
    a, b = _pitcher(9530), _pitcher(9531)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _context(701, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 2))
    _log(a.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(b.id, 701, game_date=date(2026, 4, 2), opponent='TeamB')
    fp = _run()['batch_fingerprint']
    real = backfill._apply_plan_game

    def flaky(plan, session):
        if plan.game_pk == 701:
            raise RuntimeError('commit boom')
        return real(plan, session)

    monkeypatch.setattr(backfill, '_apply_plan_game', flaky)
    summary = _run(apply=True, confirmation=PHRASE, expected_fingerprint=fp)
    assert summary['result'] == backfill.RESULT_FAIL
    assert summary['decision_reasons'] == ['game_commit_failure']
    assert _reload(_log_only(a.id, 700)).appearance_team_status == ata.STATUS_RESOLVED
    assert _reload(_log_only(b.id, 701)).appearance_team_status is None
    assert summary['next_cursor']['after_game_pk'] == 700


def test_invalid_stored_state_returns_fail(monkeypatch, app):
    p = _pitcher(9540)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    fp = _run()['batch_fingerprint']
    monkeypatch.setattr(backfill, '_invalid_stored_state_count', lambda session: 1)
    summary = _run(apply=True, confirmation=PHRASE, expected_fingerprint=fp)
    assert summary['result'] == backfill.RESULT_FAIL
    assert summary['decision_reasons'] == ['invalid_stored_states']


def test_end_date_before_start_raises(app):
    with pytest.raises(ValueError):
        _run(start_date=date(2026, 5, 1), end_date=date(2026, 4, 1))


# ═══════════════════════ L. Report consistency ══════════════════════════════
def test_report_counts_reconcile(app):
    resolved_p = _pitcher(9901)
    unresolved_p = _pitcher(9902)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(resolved_p.id, 700, opponent='TeamB')          # Tier 1 resolved
    _log(unresolved_p.id, 700, opponent='Unmatched')    # no line -> unresolved
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9901])})
    summary = _run(client=client)
    assert summary['counts_reconcile'] is True
    assert summary['appearances_targeted'] == (
        summary['proposed_resolved'] + summary['proposed_unresolved']
        + summary['proposed_conflict']
    )


def test_report_has_governance_and_cursor_fields(app):
    p = _pitcher(9903)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run()
    for key in ('capability', 'mode', 'result', 'exit_code', 'batch_fingerprint',
                'inputs', 'next_cursor', 'has_more', 'decision_reasons',
                'expected_migration_head', 'database_writes_performed',
                'coverage_before', 'coverage_after'):
        assert key in summary
    assert summary['expected_migration_head'] == backfill.EXPECTED_MIGRATION_HEAD


def test_report_lists_are_bounded(app):
    assert backfill._MAX_GAME_DETAIL <= 500
    assert backfill._MAX_ROW_DETAIL <= 1000
    assert backfill._MAX_FAILED_GAME_DETAIL <= 200


def test_report_never_contains_raw_payload_or_secret(app):
    p = _pitcher(9904)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9904])})
    summary = _run(client=client)
    blob = str(summary).lower()
    for token in ('password', 'secret', 'postgres://', 'authorization', 'statsapi'):
        assert token not in blob


# ═══════════════════════ M. CLI + workflow contract ═════════════════════════
def test_cli_confirmation_phrase_matches_service():
    from scripts import run_2026_appearance_team_backfill as cli
    assert cli.CONFIRMATION_PHRASE == backfill.CONFIRMATION_PHRASE


def test_service_exit_code_mapping():
    assert backfill.EXIT_BY_RESULT[backfill.RESULT_PASS] == 0
    assert backfill.EXIT_BY_RESULT[backfill.RESULT_REFUSED] == 1
    assert backfill.EXIT_BY_RESULT[backfill.RESULT_FAIL] == 1
    assert backfill.EXIT_BY_RESULT[backfill.RESULT_INCONCLUSIVE] == 2


def test_cli_batch_size_is_bounded():
    import argparse
    from scripts import run_2026_appearance_team_backfill as cli
    assert cli._bounded_batch_size('5') == 5
    with pytest.raises(argparse.ArgumentTypeError):
        cli._bounded_batch_size('0')
    with pytest.raises(argparse.ArgumentTypeError):
        cli._bounded_batch_size(str(cli.MAX_BATCH_SIZE + 1))


def test_cli_iso_date_validates():
    import argparse
    from scripts import run_2026_appearance_team_backfill as cli
    assert cli._iso_date('2026-04-01') == date(2026, 4, 1)
    with pytest.raises(argparse.ArgumentTypeError):
        cli._iso_date('not-a-date')


def test_cli_cursor_requires_both_parts():
    from scripts import run_2026_appearance_team_backfill as cli
    args = cli._parse_args(['--after-game-date', '2026-04-01'])
    with pytest.raises(SystemExit):
        cli._validate_cursor(args)
    both = cli._parse_args(['--after-game-date', '2026-04-01', '--after-game-pk', '700'])
    cli._validate_cursor(both)


def test_cli_dry_run_default_and_sets_auto_sync_off():
    from scripts import run_2026_appearance_team_backfill as cli
    assert cli._parse_args([]).apply is False
    source = Path(cli.__file__).read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in source
    assert 'pitcher.team_id' not in source.lower()


def test_workflow_dispatch_only_no_automatic_trigger():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in source
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:',
                    '\n  workflow_call:', '\n  repository_dispatch:'):
        assert trigger not in source


def test_workflow_apply_requires_confirmation_and_fingerprint():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'RUN_2026_APPEARANCE_TEAM_BACKFILL' in source
    assert 'requires an approved dry-run fingerprint' in source
    assert 'concurrency:' in source
    assert 'contents: read' in source
