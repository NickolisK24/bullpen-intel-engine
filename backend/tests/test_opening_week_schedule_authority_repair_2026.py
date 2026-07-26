"""2026 opening-week schedule-authority repair.

Covers the fixed 47-game allowlist and target-set enforcement, official-evidence
validation (final / non-final / postponed / suspended / game-type / home / away /
duplicate / contradiction), canonical ScheduledGame persistence via the existing
ingester (idempotency, both sides, contradiction refusal, per-game rollback, stop-at-
first-failure), the fingerprint contract, the dry-run read-only guarantee, the mandatory
apply confirmation + fingerprint gates, the strict result/exit-code contract, and — end
to end in fixtures — that after schedule repair the existing Foundation 2 selector
discovers the games, the governed backfill resolves all 418 appearances (418/0/0), and
the residual audit reaches zero. The repair never writes GameLog appearance-team fields.
"""

from collections import defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority as ata
from services import appearance_team_backfill_2026 as f2backfill
from services import appearance_team_residual_audit_2026 as residual_audit
from services import opening_week_schedule_authority_repair_2026 as repair
from services import schedule_ingestion
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'opening_week_schedule_authority_repair_2026.py'
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'appearance_team_backfill_2026.yml'
PHRASE = repair.CONFIRMATION_PHRASE
_COUNTS = [9 if i < 42 else 8 for i in range(47)]  # sums to 418 across 47 games


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
def _pitcher(mlb_id):
    p = Pitcher(mlb_id=mlb_id, full_name=f'P{mlb_id}', active=True)
    db.session.add(p)
    db.session.commit()
    return p


def _log(pitcher_id, game_pk, game_date, opponent_abbr='', status=None, commit=True):
    log = GameLog(pitcher_id=pitcher_id, mlb_game_pk=game_pk, game_date=game_date,
                  opponent='Opp', opponent_abbreviation=opponent_abbr, game_type='R',
                  innings_pitched=1.0, innings_pitched_outs=3, appearance_team_status=status)
    db.session.add(log)
    if commit:
        db.session.commit()
    return log


def _official_game(game_pk, gdate, home_id, away_id, *, game_type='R', status_code='F',
                   detailed='Final', home_abbr='HOM', away_abbr='AWY',
                   doubleheader='N', game_number=1):
    return {
        'gamePk': game_pk,
        'officialDate': gdate.isoformat(),
        'gameDate': gdate.isoformat() + 'T17:00:00Z',
        'gameType': game_type,
        'status': {'statusCode': status_code, 'detailedState': detailed,
                   'abstractGameState': 'Final'},
        'teams': {'home': {'team': {'id': home_id, 'abbreviation': home_abbr}},
                  'away': {'team': {'id': away_id, 'abbreviation': away_abbr}}},
        'doubleHeader': doubleheader, 'gameNumber': game_number,
    }


class _FakeScheduleClient:
    def __init__(self, games_by_date=None, raise_dates=()):
        self.games_by_date = defaultdict(list, {k: list(v) for k, v in (games_by_date or {}).items()})
        self.raise_dates = set(raise_dates)
        self.calls = []

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        self.calls.append((start_date, end_date))
        if start_date in self.raise_dates:
            raise RuntimeError('schedule source unavailable')
        return list(self.games_by_date.get(start_date, []))


def _pitline(pid):
    return {'person': {'id': pid, 'fullName': f'P{pid}'},
            'stats': {'pitching': {'inningsPitched': '1.0', 'earnedRuns': '0', 'runs': '0',
                                   'hits': '0', 'baseOnBalls': '0', 'strikeOuts': '1',
                                   'homeRuns': '0', 'numberOfPitches': '12', 'strikes': '8'}}}


def _boxscore(home_id, away_id, home_pitcher_mlb_ids):
    return {'teams': {
        'home': {'team': {'id': home_id, 'name': f'T{home_id}'},
                 'pitchers': list(home_pitcher_mlb_ids),
                 'players': {f'ID{p}': _pitline(p) for p in home_pitcher_mlb_ids}},
        'away': {'team': {'id': away_id, 'name': f'T{away_id}'}, 'pitchers': [], 'players': {}}}}


class _FakeBoxscoreClient:
    def __init__(self, meta):
        self.by_pk = {pk: _boxscore(m['home_id'], m['away_id'], m['pitcher_mlb_ids'])
                      for pk, m in meta.items()}
        self.calls = []

    def get_game_boxscore(self, game_pk):
        self.calls.append(game_pk)
        return self.by_pk[game_pk]


def _seed_full(*, opponent_matches=True):
    """Seed all 47 target games with 418 legacy-NULL appearances + official evidence."""
    pitchers = [_pitcher(1000 + i) for i in range(9)]
    meta = {}
    games_by_date = defaultdict(list)
    for idx, (gdate, pk) in enumerate(repair.TARGET_GAMES):
        home_id, away_id = 700 + 2 * idx, 701 + 2 * idx
        count = _COUNTS[idx]
        mlb_ids = []
        for j in range(count):
            _log(pitchers[j].id, pk, gdate,
                 opponent_abbr=(f'AWY{idx}' if opponent_matches else 'ZZZ'), commit=False)
            mlb_ids.append(pitchers[j].mlb_id)
        games_by_date[gdate.isoformat()].append(
            _official_game(pk, gdate, home_id, away_id,
                           home_abbr=f'HOM{idx}', away_abbr=f'AWY{idx}'))
        meta[pk] = {'home_id': home_id, 'away_id': away_id, 'count': count,
                    'date': gdate, 'pitcher_mlb_ids': mlb_ids}
    db.session.commit()
    return meta, _FakeScheduleClient(games_by_date)


def _run(**kwargs):
    return repair.run_repair(**kwargs)


def _apply(client, **kwargs):
    plan = _run(client=client, **kwargs)
    return _run(client=client, apply=True, confirmation=PHRASE,
                expected_fingerprint=plan['fingerprint'], **kwargs)


# ═══════════════ Target set + preconditions ═════════════════════════════════
def test_target_set_is_exactly_47_games():
    assert len(repair.TARGET_GAMES) == 47
    assert len(repair.TARGET_GAME_PKS) == 47
    assert list(repair.TARGET_GAMES) == sorted(repair.TARGET_GAMES)  # (date, pk) ordered
    assert repair.EXPECTED_GAME_COUNT == 47
    assert repair.EXPECTED_RESIDUAL_ROW_COUNT == 418


def test_clean_dry_run_passes(app):
    _meta, client = _seed_full()
    s = _run(client=client)
    assert s['result'] == repair.RESULT_PASS
    assert s['exit_code'] == 0
    assert s['production_preconditions']['residual_rows'] == 418
    assert s['production_preconditions']['residual_games'] == 47
    assert s['planned_schedule_rows'] == {'row_count': 94, 'game_count': 47}
    assert s['database_writes_performed'] is False


def test_residual_row_count_mismatch_fails(app):
    meta, client = _seed_full()
    # Resolve one row so the residual count drops to 417.
    row = db.session.query(GameLog).filter(GameLog.appearance_team_status.is_(None)).first()
    row.appearance_team_status = ata.STATUS_RESOLVED
    row.appearance_team_id = 700
    row.appearance_team_source = ata.SOURCE_BOXSCORE
    row.appearance_team_reason = ata.REASON_RESOLVED_BOXSCORE
    db.session.commit()
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'residual_row_count_mismatch' in s['decision_reasons']


def test_residual_game_set_mismatch_fails(app):
    # Seed only a subset of games -> residual games != the 47 target set.
    p = _pitcher(1)
    gdate, pk = repair.TARGET_GAMES[0]
    _log(p.id, pk, gdate)
    client = _FakeScheduleClient({gdate.isoformat(): [_official_game(pk, gdate, 700, 701)]})
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'residual_game_set_mismatch' in s['decision_reasons']


def test_target_game_already_has_schedule_fails(app):
    meta, client = _seed_full()
    gdate, pk = repair.TARGET_GAMES[0]
    db.session.add(ScheduledGame(team_id=700, game_pk=pk, game_date=gdate,
                                 status_state='final', home_away='home', opponent_team_id=701))
    db.session.commit()
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'target_game_already_has_schedule' in s['decision_reasons']


def test_empty_population_inconclusive(app):
    s = _run(client=_FakeScheduleClient({}))
    assert s['result'] == repair.RESULT_INCONCLUSIVE
    assert 'no_residual_population' in s['decision_reasons']


def test_source_unavailable_inconclusive(app):
    meta, _client = _seed_full()
    unavailable = _FakeScheduleClient(raise_dates={repair.TARGET_GAMES[0][0].isoformat()})
    s = _run(client=unavailable)
    assert s['result'] == repair.RESULT_INCONCLUSIVE
    assert 'official_source_unavailable' in s['decision_reasons']


# ═══════════════ Official-evidence validation ═══════════════════════════════
def _seed_full_with_altered_first(**official_overrides):
    meta, client = _seed_full()
    gdate, pk = repair.TARGET_GAMES[0]
    client.games_by_date[gdate.isoformat()] = [
        _official_game(pk, gdate, 700, 701, **official_overrides)]
    return client


def test_non_final_game_fails(app):
    client = _seed_full_with_altered_first(status_code='I', detailed='In Progress')
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'non_final_game' in s['decision_reasons']


def test_postponed_game_fails(app):
    client = _seed_full_with_altered_first(status_code='DR', detailed='Postponed')
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'non_final_game' in s['decision_reasons']


def test_suspended_game_fails(app):
    client = _seed_full_with_altered_first(status_code='DS', detailed='Suspended')
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'non_final_game' in s['decision_reasons']


def test_unsupported_game_type_fails(app):
    client = _seed_full_with_altered_first(game_type='S')
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'unsupported_game_type' in s['decision_reasons']


def test_missing_home_team_fails(app):
    meta, client = _seed_full()
    gdate, pk = repair.TARGET_GAMES[0]
    g = _official_game(pk, gdate, 700, 701)
    g['teams']['home']['team'] = {}
    client.games_by_date[gdate.isoformat()] = [g]
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'missing_home_team' in s['decision_reasons']


def test_missing_away_team_fails(app):
    meta, client = _seed_full()
    gdate, pk = repair.TARGET_GAMES[0]
    g = _official_game(pk, gdate, 700, 701)
    g['teams']['away']['team'] = {}
    client.games_by_date[gdate.isoformat()] = [g]
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'missing_away_team' in s['decision_reasons']


def test_missing_official_evidence_fails(app):
    meta, client = _seed_full()
    gdate, pk = repair.TARGET_GAMES[0]
    client.games_by_date[gdate.isoformat()] = [
        g for g in client.games_by_date[gdate.isoformat()] if g['gamePk'] != pk]
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'official_evidence_missing' in s['decision_reasons']


def test_duplicate_conflicting_source_fails(app):
    meta, client = _seed_full()
    gdate, pk = repair.TARGET_GAMES[0]
    client.games_by_date[gdate.isoformat()].append(_official_game(pk, gdate, 999, 998))
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'duplicate_conflicting_source' in s['decision_reasons']


def test_contradictory_opponent_evidence_fails(app):
    meta, client = _seed_full(opponent_matches=False)  # residual opponent 'ZZZ' != teams
    s = _run(client=client)
    assert s['result'] == repair.RESULT_FAIL
    assert 'contradictory_opponent_evidence' in s['decision_reasons']


def test_doubleheader_metadata_preserved(app):
    meta, client = _seed_full()
    gdate, pk = repair.TARGET_GAMES[0]
    client.games_by_date[gdate.isoformat()] = [
        _official_game(pk, gdate, 700, 701, doubleheader='Y', game_number=2)]
    _apply(client)
    rows = db.session.query(ScheduledGame).filter(ScheduledGame.game_pk == pk).all()
    assert all(r.doubleheader == 'Y' and r.game_number == 2 for r in rows)


def test_schedule_fetched_once_per_date(app):
    meta, client = _seed_full()
    _run(client=client)
    # 5 distinct dates -> 5 calls, each a single-date range.
    assert len(client.calls) == 5
    assert all(start == end for start, end in client.calls)


def test_report_contains_no_raw_payload_or_secret(app):
    meta, client = _seed_full()
    blob = str(_run(client=client)).lower()
    for token in ('password', 'secret', 'postgres://', 'statuscode', 'abstractgamestate'):
        assert token not in blob


# ═══════════════ Canonical persistence + idempotency ════════════════════════
def test_apply_writes_canonical_two_sided_rows(app):
    meta, client = _seed_full()
    s = _apply(client)
    assert s['result'] == repair.RESULT_PASS
    assert s['games_committed'] == 47
    assert s['schedule_rows_written'] == 94
    assert s['database_writes_performed'] is True
    gdate, pk = repair.TARGET_GAMES[0]
    rows = db.session.query(ScheduledGame).filter(ScheduledGame.game_pk == pk).all()
    sides = {(r.home_away, r.team_id, r.opponent_team_id, r.status_state, r.game_type) for r in rows}
    assert sides == {('home', 700, 701, 'final', 'R'), ('away', 701, 700, 'final', 'R')}
    assert all(r.source == repair.REPAIR_SOURCE for r in rows)


def test_apply_is_idempotent(app):
    meta, client = _seed_full()
    _apply(client)
    before = db.session.query(ScheduledGame).count()
    # A second run now sees existing schedule rows and refuses (precondition changed).
    second = _run(client=client)
    assert second['result'] == repair.RESULT_FAIL
    assert 'target_game_already_has_schedule' in second['decision_reasons']
    assert db.session.query(ScheduledGame).count() == before


def test_apply_per_game_rollback_on_ingest_error(app):
    meta, client = _seed_full()
    plan = _run(client=client)
    real = schedule_ingestion.ingest_games
    second_pk = repair.TARGET_GAMES[1][1]

    def flaky(games, **kw):
        if games and games[0].get('gamePk') == second_pk:
            return {'errors': 1, 'rows_created': 0}
        return real(games, **kw)

    s = repair.run_repair(client=client, apply=True, confirmation=PHRASE,
                          expected_fingerprint=plan['fingerprint'], ingester=flaky)
    assert s['result'] == repair.RESULT_FAIL
    assert s['failed_game_count'] == 1
    first_pk = repair.TARGET_GAMES[0][1]
    assert db.session.query(ScheduledGame).filter(ScheduledGame.game_pk == first_pk).count() == 2
    assert db.session.query(ScheduledGame).filter(ScheduledGame.game_pk == second_pk).count() == 0


def test_apply_does_not_touch_unrelated_schedule(app):
    meta, client = _seed_full()
    db.session.add(ScheduledGame(team_id=555, game_pk=999999, game_date=date(2026, 5, 1),
                                 status_state='final', home_away='home', opponent_team_id=556))
    db.session.commit()
    _apply(client)
    unrelated = db.session.query(ScheduledGame).filter(ScheduledGame.game_pk == 999999).one()
    assert unrelated.team_id == 555 and unrelated.status_state == 'final'


# ═══════════════ Fingerprint contract ═══════════════════════════════════════
def test_fingerprint_stable_across_dry_runs(app):
    meta, client = _seed_full()
    assert _run(client=client)['fingerprint'] == _run(client=client)['fingerprint']


def test_fingerprint_changes_when_official_payload_changes(app):
    meta, client = _seed_full()
    base = _run(client=client)['fingerprint']
    gdate, pk = repair.TARGET_GAMES[0]
    client.games_by_date[gdate.isoformat()] = [_official_game(pk, gdate, 700, 888)]  # away changed
    assert _run(client=client)['fingerprint'] != base


def test_fingerprint_independent_of_game_order():
    plan_a = [SimpleNamespace(game_pk=1, game_date='2026-03-25', game_type='R',
                              final_status_code='F', status_state='final', home_team_id=10,
                              away_team_id=11, doubleheader='N', game_number=1,
                              planned_rows=({'team_id': 10, 'opponent_team_id': 11, 'home_away': 'home'},),
                              context_action='skipped_not_required', reason_code='')]
    fp1 = repair._repair_fingerprint(plans=plan_a, season=2026, campaign_start=date(2026, 3, 25),
                                     campaign_end=date(2026, 3, 29), expected_game_count=47,
                                     expected_residual_row_count=418, migration_head=None)
    fp2 = repair._repair_fingerprint(plans=plan_a, season=2026, campaign_start=date(2026, 3, 25),
                                     campaign_end=date(2026, 3, 29), expected_game_count=47,
                                     expected_residual_row_count=418, migration_head=None)
    assert fp1 == fp2


def test_apply_without_confirmation_refused(app):
    meta, client = _seed_full()
    plan = _run(client=client)
    s = _run(client=client, apply=True, expected_fingerprint=plan['fingerprint'])
    assert s['result'] == repair.RESULT_REFUSED
    assert s['decision_reasons'] == ['confirmation_phrase_required']
    assert db.session.query(ScheduledGame).count() == 0


def test_apply_without_fingerprint_refused(app):
    meta, client = _seed_full()
    s = _run(client=client, apply=True, confirmation=PHRASE)
    assert s['result'] == repair.RESULT_REFUSED
    assert s['decision_reasons'] == ['approved_fingerprint_required']
    assert db.session.query(ScheduledGame).count() == 0


def test_apply_with_mismatched_fingerprint_refused(app):
    meta, client = _seed_full()
    s = _run(client=client, apply=True, confirmation=PHRASE, expected_fingerprint='deadbeef')
    assert s['result'] == repair.RESULT_REFUSED
    assert s['decision_reasons'] == ['fingerprint_mismatch']
    assert db.session.query(ScheduledGame).count() == 0


def test_apply_with_stale_fingerprint_after_evidence_change_refused(app):
    meta, client = _seed_full()
    stale = _run(client=client)['fingerprint']
    gdate, pk = repair.TARGET_GAMES[0]
    # Change the official away team id (fingerprint-relevant) but keep abbreviations
    # matching so the only effect is a fingerprint change, not a contradiction.
    client.games_by_date[gdate.isoformat()] = [
        _official_game(pk, gdate, 700, 888, home_abbr='HOM0', away_abbr='AWY0')]
    s = _run(client=client, apply=True, confirmation=PHRASE, expected_fingerprint=stale)
    assert s['result'] == repair.RESULT_REFUSED
    assert s['decision_reasons'] == ['fingerprint_mismatch']
    assert db.session.query(ScheduledGame).count() == 0


# ═══════════════ Read-only dry run ══════════════════════════════════════════
def test_dry_run_emits_no_write_sql(app):
    meta, client = _seed_full()
    statements = []

    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        _run(client=client)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)
    writes = [s for s in statements
              if s.strip().split()[0].upper() in ('INSERT', 'UPDATE', 'DELETE')]
    assert writes == []


def test_dry_run_writes_no_schedule_rows(app):
    meta, client = _seed_full()
    _run(client=client)
    assert db.session.query(ScheduledGame).count() == 0


def test_service_never_writes_gamelog_appearance_team(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    # No appearance-team assignment anywhere in the schedule-repair service.
    assert 'appearance_team_id =' not in source
    assert 'appearance_team_status =' not in source
    assert 'pitcher.team_id' not in source.lower()


def test_apply_does_not_change_appearance_team_status(app):
    meta, client = _seed_full()
    _apply(client)
    # Schedule authority now exists, but the repair itself left every appearance NULL.
    assert db.session.query(GameLog).filter(GameLog.appearance_team_status.isnot(None)).count() == 0


# ═══════════════ Result / report contract ═══════════════════════════════════
def test_service_exit_code_map():
    assert repair.EXIT_BY_RESULT[repair.RESULT_PASS] == 0
    assert repair.EXIT_BY_RESULT[repair.RESULT_REFUSED] == 1
    assert repair.EXIT_BY_RESULT[repair.RESULT_FAIL] == 1
    assert repair.EXIT_BY_RESULT[repair.RESULT_INCONCLUSIVE] == 2


def test_report_has_required_fields(app):
    meta, client = _seed_full()
    s = _run(client=client)
    for key in ('capability', 'mode', 'result', 'exit_code', 'migration_head',
                'expected_migration_head', 'inputs', 'target_games',
                'production_preconditions', 'official_evidence', 'planned_schedule_rows',
                'planned_completed_context', 'bounded_game_preview', 'fingerprint',
                'decision_reasons', 'next_step', 'database_writes_performed'):
        assert key in s, key
    assert s['expected_migration_head'] == 'a4f1c7e9b3d2'
    assert s['planned_completed_context'] == {'create_count': 0, 'refresh_count': 0,
                                              'skipped_count': 47}


def test_completed_context_skipped_reason(app):
    # The resolver reads ScheduledGame only, so the repair is schedule-only.
    meta, client = _seed_full()
    s = _run(client=client)
    assert s['planned_completed_context']['create_count'] == 0
    assert s['official_evidence']['final_games'] == 47


# ═══════════════ End-to-end: repair → Foundation 2 backfill → residual audit ═
def test_downstream_backfill_resolves_all_418(app):
    meta, client = _seed_full()
    _apply(client)  # schedule authority now exists for all 47 games
    box = _FakeBoxscoreClient(meta)
    plan = f2backfill.run_backfill(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
                                   batch_size=1000, client=box)
    assert plan['games_selected'] == 47
    assert plan['appearances_targeted'] == 418
    assert plan['proposed_resolved'] == 418
    assert plan['proposed_unresolved'] == 0
    assert plan['proposed_conflict'] == 0


def test_downstream_full_chain_reaches_zero_residual(app):
    meta, client = _seed_full()
    _apply(client)
    box = _FakeBoxscoreClient(meta)
    plan = f2backfill.run_backfill(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
                                   batch_size=1000, client=box)
    applied = f2backfill.run_backfill(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
                                      batch_size=1000, client=box, apply=True,
                                      confirmation=f2backfill.CONFIRMATION_PHRASE,
                                      expected_fingerprint=plan['batch_fingerprint'])
    assert applied['result'] == f2backfill.RESULT_PASS
    assert applied['games_committed'] == 47
    assert applied['coverage_after']['season_null_legacy'] == 0
    assert applied['coverage_after']['invalid_stored_states'] == 0
    audit = residual_audit.run_residual_audit()
    assert audit['residual_population']['total_rows'] == 0
    assert audit['coverage']['season_null_legacy'] == 0
    assert audit['result'] == residual_audit.RESULT_INCONCLUSIVE  # empty population


def test_downstream_backfill_write_controls_unchanged(app):
    meta, client = _seed_full()
    _apply(client)
    box = _FakeBoxscoreClient(meta)
    # Foundation 2 apply still refuses without an approved fingerprint.
    refused = f2backfill.run_backfill(start_date=date(2026, 3, 1), end_date=date(2026, 3, 31),
                                      batch_size=1000, client=box, apply=True,
                                      confirmation=f2backfill.CONFIRMATION_PHRASE)
    assert refused['result'] == f2backfill.RESULT_REFUSED


# ═══════════════ CLI + workflow contract ════════════════════════════════════
def test_cli_confirmation_and_helpers():
    import argparse
    from scripts import run_2026_opening_week_schedule_repair as cli
    assert cli.CONFIRMATION_PHRASE == repair.CONFIRMATION_PHRASE
    assert cli._iso_date('2026-03-25') == date(2026, 3, 25)
    with pytest.raises(argparse.ArgumentTypeError):
        cli._iso_date('nope')
    assert cli._positive_int('47') == 47
    with pytest.raises(argparse.ArgumentTypeError):
        cli._positive_int('0')
    assert cli._parse_args([]).apply is False


def test_cli_sets_auto_sync_off_and_no_current_team():
    from scripts import run_2026_opening_week_schedule_repair as cli
    source = Path(cli.__file__).read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in source
    assert 'pitcher.team_id' not in source.lower()


def test_workflow_dispatch_only():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in source
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:',
                    '\n  workflow_call:', '\n  repository_dispatch:'):
        assert trigger not in source


def test_workflow_has_schedule_repair_operations():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'schedule_repair_dry_run' in source
    assert 'schedule_repair_apply' in source
    assert 'run_2026_opening_week_schedule_repair.py' in source
    assert 'RUN_2026_OPENING_WEEK_SCHEDULE_REPAIR' in source
    assert 'contents: read' in source
    assert 'concurrency:' in source


def test_workflow_apply_requires_confirmation_and_fingerprint():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'requires an approved dry-run fingerprint (repair_expected_fingerprint)' in source
