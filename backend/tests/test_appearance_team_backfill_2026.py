"""Foundation 2 — governed 2026 historical team-at-appearance backfill.

Exercises the backfill contract end to end against the REAL Foundation 1 resolver and
box-score parser (no test doubles for resolution): deterministic keyset target
selection (2026 window, legacy-NULL only, final games only), local-evidence-first
resolution (Tier 1 schedule via ``CompletedGameContext``; Tier 2 one box-score call),
dry-run-by-default zero-write semantics, the apply confirmation + fingerprint gates,
per-game atomic isolation, idempotent re-runs, the stored-state invariant, the
before/after coverage audit, and the guarantees that no second resolver is invented
and ``Pitcher.team_id`` is never consulted.
"""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask

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
SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / 'services'
    / 'appearance_team_backfill_2026.py'
)


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
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'P{mlb_id}', team_id=current_team_id, active=True,
    )
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
        self._boxscores = boxscores or {}
        self._raise_for = set(raise_for)
        self.calls = []

    def get_game_boxscore(self, game_pk):
        self.calls.append(game_pk)
        if game_pk in self._raise_for:
            raise RuntimeError('boxscore unavailable')
        return self._boxscores[game_pk]


def _reload(log):
    return db.session.get(GameLog, log.id)


def _run(**kwargs):
    kwargs.setdefault('client', _FakeClient())
    kwargs.setdefault('start_date', date(2026, 1, 1))
    kwargs.setdefault('end_date', date(2026, 12, 31))
    return backfill.run_backfill(**kwargs)


# ═══════════════════════════ A. Target selection ════════════════════════════
def test_selects_legacy_null_row_in_window(app):
    p = _pitcher(9001)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700)
    summary = _run()
    assert summary['games_selected'] == 1
    assert summary['appearances_targeted'] == 1


def test_excludes_row_before_window(app):
    p = _pitcher(9002)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2025, 9, 1))
    _log(p.id, 700, game_date=date(2025, 9, 1))
    summary = _run(start_date=date(2026, 1, 1))
    assert summary['games_selected'] == 0


def test_excludes_row_after_window(app):
    p = _pitcher(9003)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2027, 4, 1))
    _log(p.id, 700, game_date=date(2027, 4, 1))
    summary = _run(end_date=date(2026, 12, 31))
    assert summary['games_selected'] == 0


def test_excludes_already_resolved_row(app):
    p = _pitcher(9004)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, status=ata.STATUS_RESOLVED, team_id=TEAM_A,
         source=ata.SOURCE_BOXSCORE, reason=ata.REASON_RESOLVED_BOXSCORE)
    summary = _run()
    assert summary['games_selected'] == 0


def test_excludes_already_unresolved_row(app):
    p = _pitcher(9005)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, status=ata.STATUS_UNRESOLVED, reason=ata.REASON_UNRESOLVED)
    summary = _run()
    assert summary['games_selected'] == 0


def test_excludes_already_conflict_row(app):
    p = _pitcher(9006)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, status=ata.STATUS_CONFLICT, source=ata.SOURCE_CONFLICT,
         reason=ata.REASON_CONFLICT)
    summary = _run()
    assert summary['games_selected'] == 0


def test_excludes_scheduled_not_final_game(app):
    p = _pitcher(9007)
    _schedule(700, TEAM_A, TEAM_B, home_state='scheduled', away_state='scheduled')
    _log(p.id, 700)
    summary = _run()
    assert summary['games_selected'] == 0


def test_excludes_suspended_game(app):
    p = _pitcher(9008)
    _schedule(700, TEAM_A, TEAM_B, home_state='final', away_state='suspended')
    _log(p.id, 700)
    summary = _run()
    assert summary['games_selected'] == 0


def test_excludes_postponed_game(app):
    p = _pitcher(9009)
    _schedule(700, TEAM_A, TEAM_B, home_state='postponed', away_state='postponed')
    _log(p.id, 700)
    summary = _run()
    assert summary['games_selected'] == 0


def test_excludes_game_with_no_schedule_evidence(app):
    p = _pitcher(9010)
    _log(p.id, 700)  # no ScheduledGame rows at all -> fail closed, not selected
    summary = _run()
    assert summary['games_selected'] == 0


def test_two_appearances_one_game_is_one_selected_game_two_targets(app):
    p1 = _pitcher(9011)
    p2 = _pitcher(9012)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p1.id, 700)
    _log(p2.id, 700)
    summary = _run()
    assert summary['games_selected'] == 1
    assert summary['appearances_targeted'] == 2


def test_keyset_cursor_excludes_past_games(app):
    p = _pitcher(9013)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _log(p.id, 700, game_date=date(2026, 4, 1))
    _log(p.id, 701, game_date=date(2026, 4, 2))
    summary = _run(after_game_date=date(2026, 4, 1), after_game_pk=700)
    assert summary['games_selected'] == 1
    assert summary['next_cursor']['after_game_pk'] == 701


def test_ordering_game_date_then_game_pk(app):
    p = _pitcher(9014)
    _schedule(702, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _log(p.id, 702, game_date=date(2026, 4, 2))
    _log(p.id, 701, game_date=date(2026, 4, 1))
    _log(p.id, 700, game_date=date(2026, 4, 1))
    summary = _run(batch_size=1)
    # First by (date asc, pk asc) is 2026-04-01 / pk 700.
    assert summary['next_cursor'] == {'after_game_date': '2026-04-01', 'after_game_pk': 700}


def test_batch_size_limits_distinct_games(app):
    p = _pitcher(9015)
    for i, pk in enumerate((700, 701, 702)):
        _schedule(pk, TEAM_A, TEAM_B, game_date=date(2026, 4, 1 + i))
        _log(p.id, pk, game_date=date(2026, 4, 1 + i))
    summary = _run(batch_size=2)
    assert summary['games_selected'] == 2
    assert summary['exhausted'] is False


def test_batch_size_is_clamped(app):
    assert backfill._clamp_batch_size(10 ** 9) == backfill.MAX_BATCH_SIZE
    assert backfill._clamp_batch_size(0) == 1
    assert backfill._clamp_batch_size('nan') == backfill.DEFAULT_BATCH_SIZE


def test_next_cursor_points_at_last_selected_game(app):
    p = _pitcher(9016)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _log(p.id, 700, game_date=date(2026, 4, 1))
    _log(p.id, 701, game_date=date(2026, 4, 2))
    summary = _run()
    assert summary['next_cursor'] == {'after_game_date': '2026-04-02', 'after_game_pk': 701}


def test_exhausted_true_when_batch_not_full(app):
    p = _pitcher(9017)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run(batch_size=50)
    assert summary['exhausted'] is True


def test_cursor_tiebreak_within_same_date(app):
    p = _pitcher(9018)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _log(p.id, 700, game_date=date(2026, 4, 1))
    _log(p.id, 701, game_date=date(2026, 4, 1))
    summary = _run(after_game_date=date(2026, 4, 1), after_game_pk=700)
    assert summary['games_selected'] == 1
    assert summary['next_cursor']['after_game_pk'] == 701


# ═══════════════════ B. Tier 1 local resolution (no API) ════════════════════
def test_tier1_resolves_via_context_opponent_name(app):
    p = _pitcher(9101)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'Rivals')  # A faced 'Rivals' (=B)
    _log(p.id, 700, opponent='Rivals')
    client = _FakeClient()  # empty; any API call would KeyError
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
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
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_id == TEAM_A
    assert row.appearance_team_source == ata.SOURCE_SCHEDULE
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
    # Context opponent_name does not match the log's opponent -> Tier 1 declines.
    _context(700, TEAM_A, TEAM_B, 'DifferentName')
    _log(p.id, 700, opponent='NoSuchTeam')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9104])})
    _run(client=client)
    assert client.calls == [700]


def test_tier1_missing_context_falls_to_api(app):
    p = _pitcher(9105)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, opponent='TeamB')  # no CompletedGameContext
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9105])})
    _run(client=client)
    assert client.calls == [700]


def test_tier1_name_match_resolves_correct_facing_team(app):
    # Pitcher on B (home=A, away=B). B faced A ('Aces'). Correct attribution = B.
    p = _pitcher(9106)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_B, TEAM_A, 'Aces')  # B's row: opponent A named 'Aces'
    _log(p.id, 700, opponent='Aces')
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_id == TEAM_B


def test_tier1_schedule_ambiguous_falls_to_api(app):
    p = _pitcher(9107)
    # Two schedule rows both facing the same derived opponent -> resolve_from_schedule
    # fails closed; Tier 1 declines.
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
    _log(p.id, 700, opponent='TeamB')  # no context -> box score
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9201])})
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_RESOLVED
    assert row.appearance_team_id == TEAM_A
    assert row.appearance_team_source == ata.SOURCE_BOXSCORE


def test_tier2_exactly_one_call_per_game(app):
    p1 = _pitcher(9202)
    p2 = _pitcher(9203)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p1.id, 700)
    _log(p2.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9202, 9203])})
    _run(client=client)
    assert client.calls == [700]


def test_tier2_resolves_each_pitcher_to_own_side(app):
    home_p = _pitcher(9204)
    away_p = _pitcher(9205)
    _schedule(700, TEAM_A, TEAM_B)
    _log(home_p.id, 700, opponent='TeamB')
    _log(away_p.id, 700, opponent='TeamA')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9204], away_pids=[9205])})
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    assert _reload(_log_only(home_p.id, 700)).appearance_team_id == TEAM_A
    assert _reload(_log_only(away_p.id, 700)).appearance_team_id == TEAM_B


def test_tier2_boxscore_schedule_conflict_clears_team(app):
    p = _pitcher(9206)
    # Box score puts the pitcher on home=A facing away=B; the schedule ledger says the
    # side facing B is C (not A). The authoritative box side and the schedule disagree
    # on a definite team -> conflict, team cleared.
    db.session.add_all([
        ScheduledGame(team_id=TEAM_C, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='home', opponent_team_id=TEAM_B),
        ScheduledGame(team_id=TEAM_B, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='away', opponent_team_id=TEAM_C),
    ])
    db.session.commit()
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9206])})
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_CONFLICT
    assert row.appearance_team_id is None


def test_tier2_no_matching_line_is_unresolved(app):
    p = _pitcher(9207)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    # Box score has a different pitcher; ours has no line.
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[999999])})
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_UNRESOLVED
    assert row.appearance_team_id is None


def test_tier2_fetch_failure_isolates_game(app):
    good = _pitcher(9208)
    bad = _pitcher(9209)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _log(good.id, 700, game_date=date(2026, 4, 1))
    _log(bad.id, 701, game_date=date(2026, 4, 2))
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9208])}, raise_for=[701])
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    assert _reload(_log_only(good.id, 700)).appearance_team_status == ata.STATUS_RESOLVED
    assert _reload(_log_only(bad.id, 701)).appearance_team_status is None
    assert summary['games_failed'] == 1
    assert summary['result'] == backfill.RESULT_COMPLETED_WITH_FAILURES


def test_tier2_only_for_appearances_tier1_missed(app):
    starter = _pitcher(9210)  # resolved locally via starter identity
    reliever = _pitcher(9211)  # no local signal -> needs the box score
    _schedule(700, TEAM_A, TEAM_B)
    # Context resolves the starter (by starter identity) but names an opponent the
    # reliever's stored opponent does not match, so only the reliever needs the API.
    _context(700, TEAM_A, TEAM_B, 'NotTheStoredName', starter_player_id=9210)
    _log(starter.id, 700, opponent='irrelevant-for-starter')
    _log(reliever.id, 700, opponent='UnmatchedOpponent')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9210, 9211])})
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    assert client.calls == [700]  # one call, for the reliever
    assert summary['resolved_via_schedule'] >= 1
    assert summary['resolved_via_boxscore'] >= 1


def test_no_api_flag_leaves_unresolved(app):
    p = _pitcher(9212)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)  # no local evidence
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9212])})
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE,
                   client=client, allow_api=False)
    assert client.calls == []
    assert _reload(_log_only(p.id, 700)).appearance_team_status == ata.STATUS_UNRESOLVED


# ═══════════════════════ D. Dry-run semantics ═══════════════════════════════
def test_dry_run_writes_nothing(app):
    p = _pitcher(9301)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9301])})
    summary = _run(client=client)  # dry run (default)
    assert summary['mode'] == 'dry_run'
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_dry_run_reports_would_resolve_counts(app):
    p = _pitcher(9302)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700, opponent='TeamB')
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9302])})
    summary = _run(client=client)
    assert summary['appearances_resolved'] == 1
    assert summary['database_writes_performed'] is False


def test_dry_run_database_writes_performed_false(app):
    p = _pitcher(9303)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run()
    assert summary['database_writes_performed'] is False


def test_dry_run_does_not_persist_after_resolution(app):
    p = _pitcher(9304)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _run()
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_dry_run_emits_fingerprint_and_cursor(app):
    p = _pitcher(9305)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run()
    assert isinstance(summary['batch_fingerprint'], str) and summary['batch_fingerprint']
    assert summary['next_cursor'] is not None


def test_dry_run_preserves_seed_rows(app):
    # A prior test-harness hazard: the dry-run rollback must not discard committed
    # fixtures. All fixtures are committed, so they survive.
    p = _pitcher(9306)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    _run()
    assert db.session.query(GameLog).count() == 1
    assert db.session.query(ScheduledGame).count() == 2


# ═══════════════════════ E. Apply + gates ═══════════════════════════════════
def test_apply_without_confirmation_refused(app):
    p = _pitcher(9401)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run(apply=True)
    assert summary['result'] == backfill.RESULT_REFUSED
    assert summary['refused_reason'] == 'confirmation_phrase_required'
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_apply_with_wrong_confirmation_refused(app):
    p = _pitcher(9402)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run(apply=True, confirmation='nope')
    assert summary['result'] == backfill.RESULT_REFUSED
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_apply_with_confirmation_writes(app):
    p = _pitcher(9403)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    assert summary['result'] == backfill.RESULT_COMPLETED
    assert summary['database_writes_performed'] is True
    assert _reload(_log_only(p.id, 700)).appearance_team_status == ata.STATUS_RESOLVED


def test_apply_with_matching_fingerprint_writes(app):
    p = _pitcher(9404)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    plan = _run()  # dry run to learn the fingerprint
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE,
                   expected_fingerprint=plan['batch_fingerprint'])
    assert summary['result'] == backfill.RESULT_COMPLETED
    assert _reload(_log_only(p.id, 700)).appearance_team_status == ata.STATUS_RESOLVED


def test_apply_with_mismatched_fingerprint_refused(app):
    p = _pitcher(9405)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE,
                   expected_fingerprint='deadbeef')
    assert summary['result'] == backfill.RESULT_REFUSED
    assert summary['refused_reason'] == 'fingerprint_mismatch'
    assert _reload(_log_only(p.id, 700)).appearance_team_status is None


def test_refused_summary_reports_no_writes(app):
    p = _pitcher(9406)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run(apply=True)
    assert summary['database_writes_performed'] is False


def test_apply_persists_resolved_provenance(app):
    p = _pitcher(9407)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    row = _reload(_log_only(p.id, 700))
    assert (row.appearance_team_id, row.appearance_team_source, row.appearance_team_reason) == (
        TEAM_A, ata.SOURCE_SCHEDULE, ata.REASON_RESOLVED_SCHEDULE,
    )


def test_apply_persists_unresolved(app):
    p = _pitcher(9408)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[999])})
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_UNRESOLVED
    assert row.appearance_team_id is None
    assert row.appearance_team_source is None
    assert row.appearance_team_reason == ata.REASON_UNRESOLVED


def test_apply_persists_conflict(app):
    p = _pitcher(9409)
    # Box side (A) vs schedule facing-side (C) disagree on a definite team -> conflict.
    db.session.add_all([
        ScheduledGame(team_id=TEAM_C, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='home', opponent_team_id=TEAM_B),
        ScheduledGame(team_id=TEAM_B, game_pk=700, game_date=IN_WINDOW,
                      status_state='final', home_away='away', opponent_team_id=TEAM_C),
    ])
    db.session.commit()
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[9409])})
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_CONFLICT
    assert row.appearance_team_id is None
    assert row.appearance_team_source == ata.SOURCE_CONFLICT


def test_apply_commits_per_game(app):
    ok = _pitcher(9410)
    bad = _pitcher(9411)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(ok.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(bad.id, 701, game_date=date(2026, 4, 2))
    client = _FakeClient(raise_for=[701])  # game 701 needs API and fails
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    assert _reload(_log_only(ok.id, 700)).appearance_team_status == ata.STATUS_RESOLVED
    assert _reload(_log_only(bad.id, 701)).appearance_team_status is None
    assert summary['games_committed'] == 1


# ═══════════════════════ F. Fingerprint ═════════════════════════════════════
def test_fingerprint_stable_across_dry_runs(app):
    p = _pitcher(9501)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    assert _run()['batch_fingerprint'] == _run()['batch_fingerprint']


def test_fingerprint_changes_when_target_set_changes(app):
    p = _pitcher(9502)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    first = _run()['batch_fingerprint']
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 3))
    _log(p.id, 701, game_date=date(2026, 4, 3))
    assert _run()['batch_fingerprint'] != first


def test_fingerprint_changes_with_cursor(app):
    p = _pitcher(9503)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _log(p.id, 700, game_date=date(2026, 4, 1))
    _log(p.id, 701, game_date=date(2026, 4, 2))
    base = _run()['batch_fingerprint']
    moved = _run(after_game_date=date(2026, 4, 1), after_game_pk=700)['batch_fingerprint']
    assert base != moved


def test_fingerprint_depends_on_resolver_contract_version(monkeypatch, app):
    p = _pitcher(9504)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    base = _run()['batch_fingerprint']
    monkeypatch.setattr(backfill, 'RESOLVER_CONTRACT_VERSION', 'changed_contract_vX')
    assert _run()['batch_fingerprint'] != base


def test_fingerprint_independent_of_insertion_order(app):
    p1 = _pitcher(9505)
    p2 = _pitcher(9506)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p2.id, 700)
    _log(p1.id, 700)
    first = _run()['batch_fingerprint']
    # ids are sorted in the plan, so the fingerprint is order-independent; recompute.
    assert _run()['batch_fingerprint'] == first


# ═══════════════════════ G. Idempotency / re-run ════════════════════════════
def test_rerun_after_apply_selects_nothing(app):
    p = _pitcher(9601)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    second = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    assert second['games_selected'] == 0
    assert second['database_writes_performed'] is False


def test_double_apply_is_idempotent(app):
    p = _pitcher(9602)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    before = _reload(_log_only(p.id, 700)).appearance_team_id
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    assert _reload(_log_only(p.id, 700)).appearance_team_id == before


def test_dry_run_and_apply_same_state_same_fingerprint(app):
    p = _pitcher(9603)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    dry = _run()['batch_fingerprint']
    applied = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)['batch_fingerprint']
    assert dry == applied


def test_rerun_fingerprint_empty_after_full_apply(app):
    p = _pitcher(9604)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    second = _run()
    assert second['games_selected'] == 0
    assert second['next_cursor'] is None


# ═══════════════════ H. Invariant / stored-state safety ═════════════════════
def test_apply_keeps_invalid_stored_states_zero(app):
    p1 = _pitcher(9701)
    p2 = _pitcher(9702)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p1.id, 700, opponent='TeamB')
    _log(p2.id, 700, opponent='TeamB')
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    assert summary['coverage_after']['invalid_stored_states'] == 0


def test_resolved_rows_carry_team(app):
    p = _pitcher(9703)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_status == ata.STATUS_RESOLVED and row.appearance_team_id is not None


def test_nonresolved_rows_have_no_team(app):
    p = _pitcher(9704)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    client = _FakeClient({700: _boxscore(TEAM_A, TEAM_B, home_pids=[123])})
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, client=client)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_id is None


def test_never_overwrites_explicit_unresolved_alongside_targets(app):
    explicit = _pitcher(9705)
    target = _pitcher(9706)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(explicit.id, 700, opponent='TeamB', status=ata.STATUS_UNRESOLVED,
         reason=ata.REASON_UNRESOLVED)
    _log(target.id, 700, opponent='TeamB')
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    # The explicit unresolved row is untouched; the legacy row is attributed.
    assert _reload(_log_only(explicit.id, 700)).appearance_team_status == ata.STATUS_UNRESOLVED
    assert _reload(_log_only(target.id, 700)).appearance_team_status == ata.STATUS_RESOLVED


def test_invalid_state_probe_counts_zero_on_clean_db(app):
    p = _pitcher(9707)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    assert backfill._invalid_stored_state_count(db.session) == 0


# ═══════════════ I. Reuse / never Pitcher.team_id ═══════════════════════════
def test_service_source_never_references_pitcher_team_id(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    lowered = source.lower()
    # The forbidden attribution source: a pitcher's mutable current team.
    assert 'pitcher.team_id' not in lowered
    # The only per-pitcher column the backfill reads is the immutable MLB id.
    assert 'Pitcher.mlb_id' in source


def test_service_reuses_foundation1_boxscore_parser(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'sync_service._extract_pitching_lines_from_boxscore' in source


def test_service_reuses_foundation1_boxscore_seam(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'sync_service._appearance_team_for_boxscore_line' in source


def test_service_defines_no_second_resolver(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'ata.resolve_for_write' in source
    assert 'def resolve_for_write' not in source
    assert 'def resolve_from_schedule' not in source


def test_attribution_ignores_current_team_traded_pitcher(app):
    # Pitcher's CURRENT team is C; the 2026 appearance was for A. Attribution = A.
    p = _pitcher(9708, current_team_id=TEAM_C)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    row = _reload(_log_only(p.id, 700))
    assert row.appearance_team_id == TEAM_A
    assert row.appearance_team_id != p.team_id


# ═══════════════════ J. Coverage audit before/after ═════════════════════════
def test_summary_includes_before_and_after_coverage(app):
    p = _pitcher(9801)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run()
    assert 'coverage_before' in summary and 'coverage_after' in summary


def test_apply_reduces_season_null_legacy(app):
    p = _pitcher(9802)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    before = summary['coverage_before']['season_null_legacy']
    after = summary['coverage_after']['season_null_legacy']
    assert before == 1 and after == 0


def test_coverage_after_invalid_states_zero(app):
    p = _pitcher(9803)
    _schedule(700, TEAM_A, TEAM_B)
    _context(700, TEAM_A, TEAM_B, 'TeamB')
    _log(p.id, 700, opponent='TeamB')
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    assert summary['coverage_after']['invalid_stored_states'] == 0


def test_campaign_goal_full_apply_zeroes_2026_null_legacy(app):
    p1 = _pitcher(9804)
    p2 = _pitcher(9805)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _context(701, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 2))
    _log(p1.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(p2.id, 701, game_date=date(2026, 4, 2), opponent='TeamB')
    summary = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE)
    assert summary['coverage_after']['season_null_legacy'] == 0


# ═══════════════════════ K. Finality edge / misc ════════════════════════════
def test_mixed_final_and_suspended_games(app):
    ok = _pitcher(9901)
    skip = _pitcher(9902)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2),
              home_state='final', away_state='suspended')
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _log(ok.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(skip.id, 701, game_date=date(2026, 4, 2))
    summary = _run()
    assert summary['games_selected'] == 1


def test_end_date_before_start_date_raises(app):
    with pytest.raises(ValueError):
        _run(start_date=date(2026, 5, 1), end_date=date(2026, 4, 1))


def test_batch_spans_two_dates_and_resumes(app):
    p = _pitcher(9903)
    _schedule(700, TEAM_A, TEAM_B, game_date=date(2026, 4, 1))
    _schedule(701, TEAM_A, TEAM_B, game_date=date(2026, 4, 2))
    _context(700, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 1))
    _context(701, TEAM_A, TEAM_B, 'TeamB', game_date=date(2026, 4, 2))
    _log(p.id, 700, game_date=date(2026, 4, 1), opponent='TeamB')
    _log(p.id, 701, game_date=date(2026, 4, 2), opponent='TeamB')
    first = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, batch_size=1)
    assert first['games_selected'] == 1
    cursor = first['next_cursor']
    second = _run(apply=True, confirmation=backfill.CONFIRMATION_PHRASE, batch_size=1,
                  after_game_date=date.fromisoformat(cursor['after_game_date']),
                  after_game_pk=cursor['after_game_pk'])
    assert second['games_selected'] == 1
    assert second['next_cursor']['after_game_pk'] == 701


def test_season_slice_reports_2026(app):
    p = _pitcher(9904)
    _schedule(700, TEAM_A, TEAM_B)
    _log(p.id, 700)
    summary = _run(season=2026)
    assert summary['season'] == 2026
    assert summary['coverage_before']['season_null_legacy'] == 1


def _log_only(pitcher_id, game_pk):
    return (
        db.session.query(GameLog)
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.mlb_game_pk == game_pk)
        .one()
    )


# ═══════════════════════ L. CLI wrapper contract ════════════════════════════
def test_cli_confirmation_phrase_matches_service():
    from scripts import run_2026_appearance_team_backfill as cli

    assert cli.CONFIRMATION_PHRASE == backfill.CONFIRMATION_PHRASE


def test_cli_exit_code_mapping():
    from scripts import run_2026_appearance_team_backfill as cli

    assert cli.EXIT_BY_RESULT[backfill.RESULT_COMPLETED] == 0
    assert cli.EXIT_BY_RESULT[backfill.RESULT_REFUSED] == 1
    assert cli.EXIT_BY_RESULT[backfill.RESULT_COMPLETED_WITH_FAILURES] == 2
    assert cli.EXIT_BY_RESULT[backfill.RESULT_FAILED] == 2


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
    cli._validate_cursor(both)  # no raise


def test_cli_is_dry_run_by_default_and_sets_auto_sync_off():
    from scripts import run_2026_appearance_team_backfill as cli

    args = cli._parse_args([])
    assert args.apply is False
    source = Path(cli.__file__).read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in source
    assert 'pitcher.team_id' not in source.lower()
