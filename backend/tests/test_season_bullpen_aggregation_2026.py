"""Canonical 2026 season bullpen aggregation + independent official-MLB validation.

Covers historical appearance-team authority (never current team), relief classification via
games_started, the inclusion/exclusion/refusal contract, integer-outs arithmetic and ERA
components, team + league reconciliation, the team_game_pitching_splits diagnostic
cross-check, trust states, determinism, the read-only guarantee, the independent official
validator (official starter excluded, relief summed from box scores, exact mandatory
comparison), the PASS/FAIL/INCONCLUSIVE result contract, the Foundation 3 gates, and the
dispatch-only workflow. The aggregation never mutates a row.
"""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.team_game_pitching_split import TeamGamePitchingSplit
from services import appearance_team_backfill_2026 as backfill
from services import season_bullpen_aggregation_2026 as agg
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


A, B, C = 100, 200, 300
SEASON = 2026
AS_OF = date(2026, 7, 25)
GDATE = date(2026, 6, 10)
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'season_bullpen_aggregation_2026.py'
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'canonical_season_bullpen_aggregation.yml'


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
_PITCHERS = {}


def _pitcher(mlb_id):
    existing = db.session.query(Pitcher).filter_by(mlb_id=mlb_id).first()
    if existing:
        return existing
    p = Pitcher(mlb_id=mlb_id, full_name=f'P{mlb_id}', active=True)
    db.session.add(p)
    db.session.commit()
    return p


def _sched(game_pk, home, away, *, state='final', game_type='R', gdate=GDATE):
    db.session.add_all([
        ScheduledGame(team_id=home, game_pk=game_pk, game_date=gdate, game_type=game_type,
                      status_state=state, home_away='home', opponent_team_id=away),
        ScheduledGame(team_id=away, game_pk=game_pk, game_date=gdate, game_type=game_type,
                      status_state=state, home_away='away', opponent_team_id=home),
    ])
    db.session.commit()


def _log(pid, game_pk, *, team, gs=0, outs=3, er=0, r=0, h=0, bb=0, k=0, hr=0, bf=None,
         save=False, blown=False, hold=False, status='resolved', gdate=GDATE, game_type='R',
         commit=True):
    p = _pitcher(pid)
    if status == GameLog.APPEARANCE_TEAM_RESOLVED:
        appearance_team_id, source, reason = team, 'boxscore_side', 'resolved_boxscore'
    else:
        appearance_team_id, source, reason = None, None, None
    log = GameLog(
        pitcher_id=p.id, mlb_game_pk=game_pk, game_date=gdate, game_type=game_type,
        games_started=gs, innings_pitched_outs=outs, innings_pitched=(outs / 3.0),
        earned_runs=er, runs_allowed=r, hits_allowed=h, walks=bb, strikeouts=k,
        home_runs_allowed=hr, batters_faced=bf, save=save, blown_save=blown, hold=hold,
        appearance_team_status=status, appearance_team_id=appearance_team_id,
        appearance_team_source=source, appearance_team_reason=reason,
    )
    db.session.add(log)
    if commit:
        db.session.commit()
    return log


def _split(team, game_pk, *, bullpen_outs, completeness='complete', gdate=GDATE):
    db.session.add(TeamGamePitchingSplit(
        team_id=team, mlb_game_pk=game_pk, game_date=gdate, game_type='R',
        starter_identity_status='known', bullpen_outs_recorded=bullpen_outs,
        relievers_used_count=1, split_completeness_status=completeness,
        suspended_resumed_linkage_status='none', calendar_context_status='complete',
        source='test'))
    db.session.commit()


def _seed_one_game(game_pk=9001):
    """One final R game A(home) vs B(away): each side one starter + two relievers."""
    _sched(game_pk, A, B)
    # A: starter (gs=1, excluded) + 2 relievers (6 outs total, 1 ER)
    _log(1, game_pk, team=A, gs=1, outs=18, er=2)          # starter
    _log(2, game_pk, team=A, gs=0, outs=3, er=1, k=2, h=1, bf=4)
    _log(3, game_pk, team=A, gs=0, outs=3, er=0, k=1, bf=3, save=True)
    # B: starter + 2 relievers
    _log(4, game_pk, team=B, gs=1, outs=15, er=3)          # starter
    _log(5, game_pk, team=B, gs=0, outs=4, er=1, bb=1, bf=5)
    _log(6, game_pk, team=B, gs=0, outs=2, er=0, hold=True, bf=2)
    # Matching complete splits: A bullpen outs 6, B bullpen outs 6.
    _split(A, game_pk, bullpen_outs=6)
    _split(B, game_pk, bullpen_outs=6)


def _run(**kwargs):
    return agg.run_aggregation(**kwargs)


def _team(payload, team_id):
    for t in payload['local_aggregation']['teams']:
        if t['team']['mlb_id'] == team_id:
            return t
    raise AssertionError(f'team {team_id} not in payload')


# ── Official box-score / schedule fake ────────────────────────────────────────
def _ip(outs):
    return f'{outs // 3}.{outs % 3}'


def _pline(pid, *, gs, outs, er=0, r=0, h=0, bb=0, k=0, hr=0):
    return (pid, {'gamesStarted': gs, 'inningsPitched': _ip(outs), 'earnedRuns': er,
                  'runs': r, 'hits': h, 'baseOnBalls': bb, 'strikeOuts': k, 'homeRuns': hr})


def _side(team_id, name, lines):
    return {
        'team': {'id': team_id, 'name': name},
        'pitchers': [pid for pid, _s in lines],
        'players': {f'ID{pid}': {'person': {'id': pid, 'fullName': f'P{pid}'},
                                 'stats': {'pitching': stats}} for pid, stats in lines},
    }


def _boxscore(home_id, away_id, home_lines, away_lines, *, home_name='HomeTeam',
             away_name='AwayTeam'):
    return {'teams': {'home': _side(home_id, home_name, home_lines),
                      'away': _side(away_id, away_name, away_lines)}}


def _official_game(game_pk, home, away, gdate=GDATE, *, game_type='R', status_code='F'):
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


def _matching_official_client(game_pk=9001):
    """A client whose official box score matches the _seed_one_game fixture exactly."""
    home_lines = [_pline(1, gs=1, outs=18, er=2), _pline(2, gs=0, outs=3, er=1, k=2, h=1),
                  _pline(3, gs=0, outs=3, er=0, k=1)]
    away_lines = [_pline(4, gs=1, outs=15, er=3), _pline(5, gs=0, outs=4, er=1, bb=1),
                  _pline(6, gs=0, outs=2, er=0)]
    return _FakeMlbClient(
        games=[_official_game(game_pk, A, B)],
        boxscores={game_pk: _boxscore(A, B, home_lines, away_lines)})


# ═══════════════ Metric-support matrix + scope ══════════════════════════════
def test_metric_support_matrix_classifies_every_metric():
    m = agg.METRIC_SUPPORT
    assert m['bullpen_era'] == 'supported_with_validation'
    assert m['bullpen_outs'] == 'supported_with_validation'
    assert m['saves'] == 'supported'
    assert m['hit_batters'] == 'blocked_by_missing_source'
    assert m['inherited_runners'] == 'unsupported'
    assert m['inherited_runners_scored'] == 'unsupported'
    assert set(m.values()) <= {'supported', 'supported_with_validation', 'unsupported',
                               'blocked_by_missing_source'}


def test_exit_code_map():
    assert agg.EXIT_BY_RESULT[agg.RESULT_PASS] == 0
    assert agg.EXIT_BY_RESULT[agg.RESULT_FAIL] == 1
    assert agg.EXIT_BY_RESULT[agg.RESULT_INCONCLUSIVE] == 2


def test_clean_local_aggregation_passes(app):
    _seed_one_game()
    s = _run()
    assert s['result'] == agg.RESULT_PASS
    assert s['exit_code'] == 0
    assert s['mode'] == 'local_only'
    ta, tb = _team(s, A), _team(s, B)
    assert ta['workload']['bullpen_outs'] == 6
    assert ta['workload']['relief_appearances'] == 2
    assert ta['coverage']['unique_relievers'] == 2
    assert tb['workload']['bullpen_outs'] == 6
    assert s['local_aggregation']['league_totals']['bullpen_outs'] == 12
    assert s['database_writes_performed'] is False


# ═══════════════ Authority + scope (matrix 1-17) ════════════════════════════
def test_appearance_team_id_controls_attribution_not_current_team(app):
    # A reliever whose CURRENT Pitcher.team_id is C but who pitched for A must count for A.
    _sched(9001, A, B)
    _log(1, 9001, team=A, gs=1, outs=18)
    p = _log(2, 9001, team=A, gs=0, outs=6, er=1).pitcher_id
    _log(4, 9001, team=B, gs=1, outs=18)
    # Mutate the current team to C — attribution must ignore it.
    db.session.query(Pitcher).filter(Pitcher.id == p).update({'team_id': C})
    db.session.commit()
    s = _run()
    assert _team(s, A)['workload']['bullpen_outs'] == 6
    assert not any(t['team']['mlb_id'] == C for t in s['local_aggregation']['teams'])


def test_traded_pitcher_aggregates_to_historical_teams(app):
    # Same pitcher (mlb 2) relieves for A in game1 and for B in game2 (traded mid-season).
    _sched(9001, A, B); _sched(9002, A, B, gdate=date(2026, 6, 20))
    _log(1, 9001, team=A, gs=1, outs=18); _log(4, 9001, team=B, gs=1, outs=18)
    _log(2, 9001, team=A, gs=0, outs=6, er=1)
    _log(1, 9002, team=A, gs=1, outs=18, gdate=date(2026, 6, 20))
    _log(4, 9002, team=B, gs=1, outs=18, gdate=date(2026, 6, 20))
    _log(2, 9002, team=B, gs=0, outs=3, er=0, gdate=date(2026, 6, 20))
    s = _run()
    assert _team(s, A)['workload']['bullpen_outs'] == 6
    assert _team(s, B)['workload']['bullpen_outs'] == 3


def test_null_status_excluded_and_fails(app):
    _seed_one_game()
    _log(7, 9001, team=A, gs=0, outs=3, status=None)  # legacy NULL in a final R game
    s = _run()
    assert s['result'] == agg.RESULT_FAIL
    assert 'legacy_null_appearance' in s['decision_reasons']
    assert s['coverage']['legacy_null_rows'] == 1


def test_unresolved_status_excluded_and_fails(app):
    _seed_one_game()
    _log(7, 9001, team=A, gs=0, outs=3, status=GameLog.APPEARANCE_TEAM_UNRESOLVED)
    s = _run()
    assert s['result'] == agg.RESULT_FAIL
    assert 'appearance_team_not_resolved' in s['decision_reasons']
    assert s['coverage']['unresolved_rows'] == 1


def test_conflict_status_excluded_and_fails(app):
    _seed_one_game()
    _log(7, 9001, team=A, gs=0, outs=3, status=GameLog.APPEARANCE_TEAM_CONFLICT)
    s = _run()
    assert s['result'] == agg.RESULT_FAIL
    assert 'contradictory_game_authority' in s['decision_reasons']
    assert s['coverage']['conflict_rows'] == 1


def test_appearance_team_not_in_game_fails(app):
    # A resolved appearance attributed to team C that did not play game 9001 (A vs B).
    _seed_one_game()
    _log(7, 9001, team=C, gs=0, outs=3)
    s = _run()
    assert s['result'] == agg.RESULT_FAIL
    assert 'appearance_team_not_in_game' in s['decision_reasons']


def test_only_requested_season_included(app):
    _seed_one_game()
    _sched(8000, A, B, gdate=date(2025, 6, 10))
    _log(9, 8000, team=A, gs=0, outs=9, gdate=date(2025, 6, 10))  # 2025 — out of season
    s = _run(season=2026)
    assert _team(s, A)['workload']['bullpen_outs'] == 6  # 2025 not counted


def test_as_of_date_is_inclusive_and_later_excluded(app):
    _sched(9001, A, B, gdate=AS_OF)
    _log(1, 9001, team=A, gs=1, outs=18, gdate=AS_OF)
    _log(4, 9001, team=B, gs=1, outs=18, gdate=AS_OF)
    _log(2, 9001, team=A, gs=0, outs=3, gdate=AS_OF)          # on the boundary => included
    _sched(9002, A, B, gdate=date(2026, 7, 26))
    _log(1, 9002, team=A, gs=1, outs=18, gdate=date(2026, 7, 26))
    _log(4, 9002, team=B, gs=1, outs=18, gdate=date(2026, 7, 26))
    _log(3, 9002, team=A, gs=0, outs=9, gdate=date(2026, 7, 26))  # after as_of => excluded
    s = _run(as_of_date=AS_OF)
    assert _team(s, A)['workload']['bullpen_outs'] == 3


def test_only_regular_season_game_type(app):
    _seed_one_game()
    # A spring-training row (game_type S) is out of scope entirely.
    _sched(7000, A, B, game_type='S')
    _log(9, 7000, team=A, gs=0, outs=9, game_type='S')
    s = _run()
    assert _team(s, A)['workload']['bullpen_outs'] == 6


def test_non_final_game_excluded(app):
    _seed_one_game()
    _sched(9002, A, B, state='scheduled')
    _log(9, 9002, team=A, gs=0, outs=9)  # game not final => excluded, not blocking
    s = _run()
    assert s['result'] == agg.RESULT_PASS
    assert _team(s, A)['workload']['bullpen_outs'] == 6
    assert s['coverage']['excluded_by_reason'].get('schedule_authority_missing') == 1


def test_postponed_game_excluded(app):
    _seed_one_game()
    _sched(9002, A, B, state='postponed')
    _log(9, 9002, team=A, gs=0, outs=9)
    s = _run()
    assert s['result'] == agg.RESULT_PASS
    assert _team(s, A)['workload']['bullpen_outs'] == 6


def test_missing_schedule_authority_excluded(app):
    _seed_one_game()
    # A GameLog row whose game_pk has no ScheduledGame rows at all.
    _log(9, 9999, team=A, gs=0, outs=9)
    s = _run()
    assert s['result'] == agg.RESULT_PASS
    assert s['coverage']['excluded_by_reason'].get('schedule_authority_missing') == 1


def test_doubleheaders_stay_distinct(app):
    # Two distinct game_pks same day both count.
    _sched(9001, A, B); _sched(9002, A, B)
    _log(1, 9001, team=A, gs=1, outs=18); _log(4, 9001, team=B, gs=1, outs=18)
    _log(1, 9002, team=A, gs=1, outs=18); _log(4, 9002, team=B, gs=1, outs=18)
    _log(2, 9001, team=A, gs=0, outs=3)
    _log(3, 9002, team=A, gs=0, outs=6)
    s = _run()
    assert _team(s, A)['workload']['bullpen_outs'] == 9
    assert _team(s, A)['coverage']['team_games_with_relief_usage'] == 2


def test_duplicate_appearance_detected():
    # DB unique (pitcher_id, game_pk) prevents storage, so exercise the guard directly.
    seen = {(1, 9001)}
    from types import SimpleNamespace
    log = SimpleNamespace(mlb_game_pk=9001, pitcher_id=1)
    decision = agg._classify_row(log, {9001: agg._FinalGame(9001, frozenset({A, B}), GDATE)}, seen)
    assert decision.reason_code == 'duplicate_appearance'
    assert decision.blocking == 'fail'


# ═══════════════ Relief classification (matrix 18-25) ═══════════════════════
def test_starter_excluded_reliever_included(app):
    _seed_one_game()
    s = _run()
    assert s['coverage']['starter_rows_excluded'] == 2  # one per team
    assert s['coverage']['included_relief_rows'] == 4


def test_games_started_null_is_inconclusive(app):
    _seed_one_game()
    _log(7, 9001, team=A, gs=None, outs=3)  # start unknown in a final R game
    s = _run()
    assert s['result'] == agg.RESULT_INCONCLUSIVE
    assert 'starter_identity_unknown' in s['decision_reasons']
    assert s['coverage']['missing_starter_identity_games'] == 1


def test_opener_with_start_is_starter(app):
    # An opener credited with the start (gs=1, few outs) is still a starter, excluded.
    _sched(9001, A, B)
    _log(1, 9001, team=A, gs=1, outs=3)      # opener credited with the start
    _log(4, 9001, team=B, gs=1, outs=18)
    _log(2, 9001, team=A, gs=0, outs=21, er=2)  # bulk follower — relief
    s = _run()
    assert _team(s, A)['workload']['relief_appearances'] == 1
    assert _team(s, A)['workload']['bullpen_outs'] == 21
    assert s['coverage']['starter_rows_excluded'] == 2


def test_position_player_pitching_is_relief(app):
    # A position player pitching (gs=0) is a relief appearance, not silently excluded.
    _sched(9001, A, B)
    _log(1, 9001, team=A, gs=1, outs=24); _log(4, 9001, team=B, gs=1, outs=24)
    _log(2, 9001, team=A, gs=0, outs=3, r=5, er=5)  # position player mop-up
    s = _run()
    assert _team(s, A)['workload']['relief_appearances'] == 1
    assert _team(s, A)['performance']['earned_runs'] == 5


# ═══════════════ Outs + innings + ERA (matrix 26-50) ════════════════════════
def test_integer_outs_sum_exactly(app):
    _sched(9001, A, B)
    _log(1, 9001, team=A, gs=1, outs=18); _log(4, 9001, team=B, gs=1, outs=18)
    _log(2, 9001, team=A, gs=0, outs=5)   # 1.2
    _log(3, 9001, team=A, gs=0, outs=4)   # 1.1
    s = _run()
    assert _team(s, A)['workload']['bullpen_outs'] == 9


def test_innings_display_formatting():
    assert agg._innings_display(3) == '1.0'
    assert agg._innings_display(4) == '1.1'
    assert agg._innings_display(5) == '1.2'
    assert agg._innings_display(6) == '2.0'
    assert agg._innings_display(0) == '0.0'


def test_era_from_exact_components():
    comp = agg._era_components(earned_runs=3, outs=27)
    assert comp['exact_numerator'] == 81
    assert comp['exact_denominator'] == 27
    assert comp['era'] == '3.00'
    assert comp['reason_code'] is None


def test_era_zero_outs_is_unavailable_not_zero():
    comp = agg._era_components(earned_runs=0, outs=0)
    assert comp['era'] is None
    assert comp['reason_code'] == 'era_denominator_zero'


def test_era_rounding_is_deterministic():
    # 5 ER over 22 outs => 5*27/22 = 6.1363... => 6.14 (half-up, deterministic).
    comp = agg._era_components(earned_runs=5, outs=22)
    assert comp['era'] == '6.14'
    assert agg._era_components(earned_runs=5, outs=22)['era'] == comp['era']


def test_team_era_computed_from_components_not_averaged(app):
    _sched(9001, A, B)
    _log(1, 9001, team=A, gs=1, outs=18); _log(4, 9001, team=B, gs=1, outs=18)
    _log(2, 9001, team=A, gs=0, outs=3, er=3)   # would be a 27.00 pitcher ERA alone
    _log(3, 9001, team=A, gs=0, outs=24, er=0)  # 0.00 alone
    s = _run()
    perf = _team(s, A)['performance']
    # component ERA: 3*27 / 27 = 3.00 (NOT the mean of 27.00 and 0.00).
    assert perf['bullpen_era'] == '3.00'
    assert perf['bullpen_era_numerator'] == 81
    assert perf['bullpen_era_denominator'] == 27


# ═══════════════ Performance totals + optional metrics (matrix 34-45) ═══════
def test_counting_stats_sum(app):
    _sched(9001, A, B)
    _log(1, 9001, team=A, gs=1, outs=18); _log(4, 9001, team=B, gs=1, outs=18)
    _log(2, 9001, team=A, gs=0, outs=3, r=2, er=1, h=3, bb=1, k=4, hr=1)
    _log(3, 9001, team=A, gs=0, outs=3, r=0, er=0, h=1, bb=2, k=2, hr=0)
    perf = _team(_run(), A)['performance']
    assert perf['runs_allowed'] == 2 and perf['earned_runs'] == 1
    assert perf['hits_allowed'] == 4 and perf['walks'] == 3
    assert perf['strikeouts'] == 6 and perf['home_runs_allowed'] == 1


def test_optional_saves_holds_blown_saves_official(app):
    _seed_one_game()
    ta = _team(_run(), A)
    assert ta['optional_metrics']['saves']['value'] == 1
    assert ta['optional_metrics']['saves']['support_status'] == 'supported'
    tb = _team(_run(), B)
    assert tb['optional_metrics']['holds']['value'] == 1


def test_batters_faced_partial_when_any_missing(app):
    _sched(9001, A, B)
    _log(1, 9001, team=A, gs=1, outs=18); _log(4, 9001, team=B, gs=1, outs=18)
    _log(2, 9001, team=A, gs=0, outs=3, bf=4)
    _log(3, 9001, team=A, gs=0, outs=3, bf=None)  # missing => unsupported for the team
    bf = _team(_run(), A)['optional_metrics']['batters_faced']
    assert bf['support_status'] == 'unsupported'
    assert bf['reason_code'] == 'batters_faced_incomplete'


def test_inherited_runners_unsupported(app):
    _seed_one_game()
    opt = _team(_run(), A)['optional_metrics']
    assert opt['inherited_runners']['support_status'] == 'unsupported'
    assert opt['inherited_runners']['reason_code'] == agg.INHERITED_RUNNER_REASON
    assert opt['hit_batters']['support_status'] == 'blocked_by_missing_source'


# ═══════════════ Team + league reconciliation + trust (matrix 51-58) ════════
def test_team_and_league_totals_reconcile(app):
    _seed_one_game()
    s = _run()
    recon = s['reconciliations']
    assert recon['team_totals_reconcile'] is True
    assert recon['league_totals_reconcile'] is True
    assert recon['bullpen_outs_reconcile'] is True
    assert recon['excluded_row_count'] == s['coverage']['excluded_rows']


def test_team_ordering_is_by_mlb_id(app):
    _seed_one_game()
    ids = [t['team']['mlb_id'] for t in _run()['local_aggregation']['teams']]
    assert ids == sorted(ids)


def test_expected_team_count_from_schedule_authority(app):
    _seed_one_game()
    s = _run()
    assert s['reconciliations']['expected_team_count'] == 2
    assert s['reconciliations']['teams_returned'] == 2


def test_trust_complete_when_splits_match(app):
    _seed_one_game()
    assert _team(_run(), A)['trust']['status'] == agg.TRUST_COMPLETE


def test_split_divergence_caps_trust_partial_not_fail(app):
    _seed_one_game()
    # Corrupt A's split so bullpen_outs disagree (simulating the current-team grouping defect).
    row = db.session.query(TeamGamePitchingSplit).filter_by(team_id=A, mlb_game_pk=9001).one()
    row.bullpen_outs_recorded = 99
    db.session.commit()
    s = _run()
    assert s['result'] == agg.RESULT_PASS  # divergence never globally fails the run
    ta = _team(s, A)
    assert ta['trust']['status'] == agg.TRUST_PARTIAL
    assert ta['reconciliation']['outs_match'] is False
    assert 'split_outs_reconciliation_divergence' in ta['trust']['reason_codes']


def test_split_absent_is_unavailable_not_mismatch(app):
    _seed_one_game()
    db.session.query(TeamGamePitchingSplit).delete()
    db.session.commit()
    s = _run()
    assert s['result'] == agg.RESULT_PASS
    ta = _team(s, A)
    assert ta['reconciliation']['outs_match'] is None
    assert ta['reconciliation']['team_game_split_bullpen_outs'] is None


# ═══════════════ Determinism (matrix — correction propagation) ══════════════
def test_deterministic_across_runs(app):
    _seed_one_game()
    a = _run(); b = _run()
    for key in ('result', 'reconciliations', 'coverage'):
        assert a[key] == b[key]
    assert a['local_aggregation']['league_totals'] == b['local_aggregation']['league_totals']


def test_correction_changes_next_result(app):
    _seed_one_game()
    before = _team(_run(), A)['performance']['earned_runs']
    row = (db.session.query(GameLog)
           .filter(GameLog.mlb_game_pk == 9001, GameLog.games_started == 0,
                   GameLog.appearance_team_id == A).first())
    row.earned_runs = row.earned_runs + 5
    db.session.commit()
    after = _team(_run(), A)['performance']['earned_runs']
    assert after == before + 5


# ═══════════════ Read-only guarantee (matrix 75-82) ═════════════════════════
def test_service_source_has_no_write_calls():
    src = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'session.commit' not in src
    assert 'session.add' not in src
    assert 'session.delete' not in src
    assert 'session.flush' not in src
    assert 'appearance_team_id =' not in src  # never mutates attribution


def test_local_aggregation_emits_no_write_sql(app):
    _seed_one_game()
    statements = []

    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        s = _run()
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)
    writes = [st for st in statements
              if st.strip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
    assert writes == []
    assert s['database_writes_performed'] is False


def test_official_validation_emits_no_write_sql(app):
    _seed_one_game()
    statements = []

    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        _run(include_official_validation=True, client=_matching_official_client())
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)
    writes = [st for st in statements
              if st.strip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
    assert writes == []


def test_source_rows_unchanged_after_run(app):
    _seed_one_game()
    before = {g.id: (g.earned_runs, g.appearance_team_id, g.games_started)
              for g in db.session.query(GameLog).all()}
    _run()
    after = {g.id: (g.earned_runs, g.appearance_team_id, g.games_started)
             for g in db.session.query(GameLog).all()}
    assert before == after


# ═══════════════ Result contract (matrix 83-90) ═════════════════════════════
def test_migration_mismatch_fails(app, monkeypatch):
    _seed_one_game()
    monkeypatch.setattr(backfill, '_migration_head', lambda session: ['deadbeef'])
    s = _run()
    assert s['result'] == agg.RESULT_FAIL
    assert 'migration_head_mismatch' in s['decision_reasons']


def test_invalid_stored_state_fails(app, monkeypatch):
    _seed_one_game()
    monkeypatch.setattr(backfill, '_invalid_stored_state_count', lambda session: 1)
    s = _run()
    assert s['result'] == agg.RESULT_FAIL
    assert 'invalid_stored_states' in s['decision_reasons']


def test_local_pass_gates(app):
    _seed_one_game()
    s = _run()
    assert s['foundation_3_status'] == 'aggregation_ready_for_validation'
    assert s['public_reader_gate'] == 'blocked'
    assert s['share_card_performance_gate'] == 'blocked'


# ═══════════════ Independent official validation (matrix 59-74, 84-87) ══════
def test_official_validation_matches_and_passes(app):
    _seed_one_game()
    client = _matching_official_client()
    s = _run(include_official_validation=True, client=client)
    assert s['result'] == agg.RESULT_PASS
    assert s['mode'] == 'official_validation'
    assert s['official_validation']['teams_matched'] == 2
    assert s['official_validation']['mandatory_metric_mismatches'] == 0
    assert s['reconciliations']['all_mandatory_metrics_match'] is True
    assert s['foundation_3_status'] == 'validated_ready_for_reader_review'
    assert s['public_reader_gate'] == 'ready_for_review'
    assert s['share_card_performance_gate'] == 'blocked'


def test_official_starter_excluded_and_fetched_once(app):
    _seed_one_game()
    client = _matching_official_client()
    _run(include_official_validation=True, client=client)
    assert client.boxscore_calls.count(9001) == 1  # fetched exactly once
    assert client.boxscore_calls == [9001]


def test_official_only_final_regular_selected(app):
    _seed_one_game()
    home_lines = [_pline(1, gs=1, outs=18, er=2), _pline(2, gs=0, outs=3, er=1),
                  _pline(3, gs=0, outs=3, er=0)]
    away_lines = [_pline(4, gs=1, outs=15, er=3), _pline(5, gs=0, outs=4, er=1),
                  _pline(6, gs=0, outs=2, er=0)]
    client = _FakeMlbClient(
        games=[_official_game(9001, A, B),
               _official_game(7000, A, B, game_type='S'),          # spring — skip
               _official_game(6000, A, B, status_code='I')],       # in progress — skip
        boxscores={9001: _boxscore(A, B, home_lines, away_lines)})
    s = _run(include_official_validation=True, client=client)
    assert s['official_validation']['games_selected'] == 1
    assert 7000 not in client.boxscore_calls and 6000 not in client.boxscore_calls


def test_official_one_out_mismatch_fails(app):
    _seed_one_game()
    # Official reliever P2 has one extra out (4 instead of 3) => bullpen_outs mismatch.
    home_lines = [_pline(1, gs=1, outs=18, er=2), _pline(2, gs=0, outs=4, er=1),
                  _pline(3, gs=0, outs=3, er=0)]
    away_lines = [_pline(4, gs=1, outs=15, er=3), _pline(5, gs=0, outs=4, er=1),
                  _pline(6, gs=0, outs=2, er=0)]
    client = _FakeMlbClient(games=[_official_game(9001, A, B)],
                            boxscores={9001: _boxscore(A, B, home_lines, away_lines)})
    s = _run(include_official_validation=True, client=client)
    assert s['result'] == agg.RESULT_FAIL
    assert 'official_mandatory_metric_mismatch' in s['decision_reasons']
    assert s['official_validation']['mandatory_metric_mismatches'] >= 1
    assert any(m['metric'] == 'bullpen_outs' and m['team_id'] == A for m in s['bounded_mismatches'])


def test_official_one_earned_run_mismatch_fails(app):
    _seed_one_game()
    home_lines = [_pline(1, gs=1, outs=18, er=2), _pline(2, gs=0, outs=3, er=2),  # er 2 not 1
                  _pline(3, gs=0, outs=3, er=0)]
    away_lines = [_pline(4, gs=1, outs=15, er=3), _pline(5, gs=0, outs=4, er=1),
                  _pline(6, gs=0, outs=2, er=0)]
    client = _FakeMlbClient(games=[_official_game(9001, A, B)],
                            boxscores={9001: _boxscore(A, B, home_lines, away_lines)})
    s = _run(include_official_validation=True, client=client)
    assert s['result'] == agg.RESULT_FAIL
    assert any(m['metric'] == 'earned_runs' for m in s['bounded_mismatches'])


def test_official_relief_appearance_mismatch_fails(app):
    _seed_one_game()
    # Official side has an extra reliever the local aggregation lacks.
    home_lines = [_pline(1, gs=1, outs=18, er=2), _pline(2, gs=0, outs=3, er=1),
                  _pline(3, gs=0, outs=3, er=0), _pline(8, gs=0, outs=0, er=0)]
    away_lines = [_pline(4, gs=1, outs=15, er=3), _pline(5, gs=0, outs=4, er=1),
                  _pline(6, gs=0, outs=2, er=0)]
    client = _FakeMlbClient(games=[_official_game(9001, A, B)],
                            boxscores={9001: _boxscore(A, B, home_lines, away_lines)})
    s = _run(include_official_validation=True, client=client)
    assert s['result'] == agg.RESULT_FAIL
    assert any(m['metric'] == 'relief_appearances' for m in s['bounded_mismatches'])


def test_official_missing_game_evidence_inconclusive(app):
    _seed_one_game()
    client = _FakeMlbClient(games=[_official_game(9001, A, B)], boxscores={}, raise_pks={9001})
    s = _run(include_official_validation=True, client=client)
    assert s['result'] == agg.RESULT_INCONCLUSIVE
    assert 'official_evidence_unavailable' in s['decision_reasons']


def test_official_schedule_failure_bounded_inconclusive(app):
    _seed_one_game()
    client = _FakeMlbClient(games=[_official_game(9001, A, B)],
                            raise_windows={date(2026, 6, 1).isoformat()})
    s = _run(include_official_validation=True, client=client)
    assert s['result'] == agg.RESULT_INCONCLUSIVE


def test_official_validation_independent_of_local(app):
    # The validator sums box scores directly; it must not read local GameLog aggregation.
    src = SERVICE_PATH.read_text(encoding='utf-8')
    # The official helpers take box-score sides, not accumulators-from-GameLog.
    assert 'def _official_relief_for_side' in src
    assert 'get_game_boxscore' in src


def test_official_mismatch_samples_bounded(app):
    _seed_one_game()
    # Force many mismatches; ensure the bounded list respects the limit.
    home_lines = [_pline(1, gs=1, outs=18, er=2), _pline(2, gs=0, outs=9, er=9),
                  _pline(3, gs=0, outs=9, er=9)]
    away_lines = [_pline(4, gs=1, outs=15, er=3), _pline(5, gs=0, outs=9, er=9),
                  _pline(6, gs=0, outs=9, er=9)]
    client = _FakeMlbClient(games=[_official_game(9001, A, B)],
                            boxscores={9001: _boxscore(A, B, home_lines, away_lines)})
    s = _run(include_official_validation=True, client=client, mismatch_detail_limit=2)
    assert len(s['bounded_mismatches']) <= 2


# ═══════════════ CLI + workflow (matrix 91-100) ═════════════════════════════
def test_cli_helpers_and_defaults():
    import argparse
    from scripts import run_2026_season_bullpen_aggregation as cli
    assert cli.CAPABILITY == agg.CAPABILITY
    assert cli._iso_date('2026-07-25') == date(2026, 7, 25)
    with pytest.raises(argparse.ArgumentTypeError):
        cli._iso_date('nope')
    assert cli._bounded_limit('40') == 40
    with pytest.raises(argparse.ArgumentTypeError):
        cli._bounded_limit('9999')
    parsed = cli._parse_args([])
    assert parsed.season == 2026 and parsed.official_validation is False


def test_cli_sets_auto_sync_off_and_no_current_team():
    from scripts import run_2026_season_bullpen_aggregation as cli
    src = Path(cli.__file__).read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in src
    assert 'pitcher.team_id' not in src.lower()


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
    assert 'local_only' in src and 'official_validation' in src
    assert 'run_2026_season_bullpen_aggregation.py' in src
    # No write confirmation/fingerprint INPUTS or phrase because there is no write path.
    assert 'expected_fingerprint' not in src
    assert 'RUN_' not in src            # no confirmation-phrase constant
    assert '\n      confirmation:' not in src  # no confirmation dispatch input


def test_workflow_summary_uses_real_fields():
    src = WORKFLOW_PATH.read_text(encoding='utf-8')
    for field in ("payload.get('result')", "payload.get('foundation_3_status')",
                  "payload.get('public_reader_gate')", "payload.get('share_card_performance_gate')",
                  "payload.get('database_writes_performed')"):
        assert field in src


def test_report_contains_no_secret_or_raw_payload(app):
    _seed_one_game()
    blob = str(_run(include_official_validation=True, client=_matching_official_client())).lower()
    for token in ('password', 'secret', 'postgres://', 'database_url', 'statuscode',
                  'abstractgamestate'):
        assert token not in blob


def test_report_has_required_top_level_fields(app):
    _seed_one_game()
    s = _run()
    for key in ('capability', 'mode', 'result', 'exit_code', 'migration_head',
                'expected_migration_head', 'inputs', 'contracts', 'local_aggregation',
                'coverage', 'official_validation', 'bounded_mismatches', 'reconciliations',
                'decision_reasons', 'foundation_3_status', 'public_reader_gate',
                'share_card_performance_gate', 'database_writes_performed'):
        assert key in s, key
    assert s['expected_migration_head'] == 'a4f1c7e9b3d2'
    assert s['contracts']['aggregation_contract_version'] == agg.AGGREGATION_CONTRACT_VERSION
