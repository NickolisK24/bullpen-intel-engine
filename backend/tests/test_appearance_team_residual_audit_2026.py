"""Foundation 2 residual audit — read-only classification of 2026 legacy-NULL rows.

Covers the deterministic mutually-exclusive classification (every reachable category
plus the structurally-unreachable ones via the pure classifier), the exact Foundation 2
query-parity proof (calls the real ``_select_game_keys``), the read-only guarantee
(SQL capture proves SELECT-only), the PASS/FAIL/INCONCLUSIVE result contract, coverage
reconciliation and bounded samples, and the workflow/CLI contract including the
corrected Foundation 2 summary field names.
"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401
from models.completed_game_context import CompletedGameContext
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import appearance_team_backfill_2026 as backfill
from services import appearance_team_residual_audit_2026 as audit
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


A, B, C = 111, 222, 333
IN_WINDOW = date(2026, 6, 20)
AFTER_CUTOFF = date(2026, 8, 1)
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / 'backend' / 'services' / 'appearance_team_residual_audit_2026.py'
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'appearance_team_backfill_2026.yml'


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


def _log(pitcher_id, game_pk, game_date=IN_WINDOW, game_type='R', status=None):
    log = GameLog(pitcher_id=pitcher_id, mlb_game_pk=game_pk, game_date=game_date,
                  opponent='Opp', opponent_abbreviation='OP', game_type=game_type,
                  innings_pitched=1.0, innings_pitched_outs=3, appearance_team_status=status)
    db.session.add(log)
    db.session.commit()
    return log


def _sched(game_pk, specs, game_date=IN_WINDOW):
    db.session.add_all([
        ScheduledGame(team_id=t, game_pk=game_pk, game_date=game_date,
                      status_state=st, home_away=ha, opponent_team_id=o)
        for (t, o, ha, st) in specs
    ])
    db.session.commit()


def _final(game_pk, game_date=IN_WINDOW, home=A, away=B):
    _sched(game_pk, [(home, away, 'home', 'final'), (away, home, 'away', 'final')], game_date)


def _context(game_pk, team, opp, name, game_date=IN_WINDOW):
    db.session.add(CompletedGameContext(team_id=team, game_pk=game_pk, game_date=game_date,
                                        opponent_team_id=opp, opponent_name=name))
    db.session.commit()


def _run(**kwargs):
    return audit.run_residual_audit(**kwargs)


def _cat(summary, name):
    return summary['primary_categories'][name]['row_count']


# ═══════════════ Classification — reachable categories (DB) ═════════════════
def test_after_cutoff_classifies(app):
    p = _pitcher(1)
    _final(700, AFTER_CUTOFF)
    _log(p.id, 700, game_date=AFTER_CUTOFF)
    s = _run()
    assert _cat(s, audit.CAT_AFTER_CUTOFF) == 1
    assert s['exact_backfill_eligible_rows'] == 0


def test_no_schedule_rows_classifies(app):
    p = _pitcher(2)
    _log(p.id, 701)  # no ScheduledGame
    s = _run()
    assert _cat(s, audit.CAT_NO_SCHEDULE_ROWS) == 1


def test_no_final_schedule_state_classifies(app):
    p = _pitcher(3)
    _sched(702, [(A, B, 'home', 'scheduled'), (B, A, 'away', 'scheduled')])
    _log(p.id, 702)
    s = _run()
    assert _cat(s, audit.CAT_NO_FINAL) == 1


def test_postponed_classifies(app):
    p = _pitcher(4)
    _sched(703, [(A, B, 'home', 'postponed'), (B, A, 'away', 'postponed')])
    _log(p.id, 703)
    s = _run()
    assert _cat(s, audit.CAT_POSTPONED_SUSPENDED) == 1


def test_suspended_classifies(app):
    p = _pitcher(5)
    _sched(704, [(A, B, 'home', 'suspended'), (B, A, 'away', 'suspended')])
    _log(p.id, 704)
    s = _run()
    assert _cat(s, audit.CAT_POSTPONED_SUSPENDED) == 1


def test_contradictory_finality_classifies(app):
    p = _pitcher(6)
    _sched(705, [(A, B, 'home', 'final'), (B, A, 'away', 'suspended')])
    _log(p.id, 705)
    s = _run()
    assert _cat(s, audit.CAT_CONTRADICTORY_FINALITY) == 1
    assert s['exact_backfill_eligible_rows'] == 0  # non_final_exists excludes it


def test_final_plus_postponed_is_contradictory_finality(app):
    # Final must not be shadowed by the generic postponed/suspended category.
    p = _pitcher(90)
    _sched(780, [(A, B, 'home', 'final'), (B, A, 'away', 'postponed')])
    _log(p.id, 780)
    s = _run()
    assert _cat(s, audit.CAT_CONTRADICTORY_FINALITY) == 1
    assert _cat(s, audit.CAT_POSTPONED_SUSPENDED) == 0


def test_final_plus_suspended_is_contradictory_finality(app):
    p = _pitcher(91)
    _sched(781, [(A, B, 'home', 'suspended'), (B, A, 'away', 'final')])
    _log(p.id, 781)
    s = _run()
    assert _cat(s, audit.CAT_CONTRADICTORY_FINALITY) == 1
    assert _cat(s, audit.CAT_POSTPONED_SUSPENDED) == 0


def test_contradictory_finality_counted_once_and_reconciles(app):
    p = _pitcher(92)
    _sched(782, [(A, B, 'home', 'final'), (B, A, 'away', 'postponed')])
    _log(p.id, 782)
    s = _run()
    assert _cat(s, audit.CAT_CONTRADICTORY_FINALITY) == 1
    assert sum(c['row_count'] for c in s['primary_categories'].values()) == 1
    assert s['category_totals_reconcile'] is True


def test_finality_classification_is_row_order_independent(app):
    # final-then-postponed and postponed-then-final must classify identically.
    p1, p2 = _pitcher(93), _pitcher(94)
    _sched(783, [(A, B, 'home', 'final'), (B, A, 'away', 'postponed')])
    _sched(784, [(A, B, 'home', 'postponed'), (B, A, 'away', 'final')])
    _log(p1.id, 783)
    _log(p2.id, 784)
    s = _run()
    assert _cat(s, audit.CAT_CONTRADICTORY_FINALITY) == 2
    assert _cat(s, audit.CAT_POSTPONED_SUSPENDED) == 0


def test_postponed_only_and_suspended_only_are_disqualifier_not_contradictory(app):
    p1, p2 = _pitcher(95), _pitcher(96)
    _sched(785, [(A, B, 'home', 'postponed'), (B, A, 'away', 'postponed')])
    _sched(786, [(A, B, 'home', 'suspended'), (B, A, 'away', 'suspended')])
    _log(p1.id, 785)
    _log(p2.id, 786)
    s = _run()
    assert _cat(s, audit.CAT_POSTPONED_SUSPENDED) == 2
    assert _cat(s, audit.CAT_CONTRADICTORY_FINALITY) == 0


def test_incomplete_sides_classifies(app):
    p = _pitcher(7)
    _sched(706, [(A, B, 'home', 'final')])  # only one side
    _log(p.id, 706)
    s = _run()
    assert _cat(s, audit.CAT_INCOMPLETE_SIDES) == 1


def test_contradictory_authority_classifies(app):
    p = _pitcher(8)
    _sched(707, [(A, B, 'home', 'final'), (B, C, 'away', 'final')])  # opponents disagree
    _log(p.id, 707)
    s = _run()
    assert _cat(s, audit.CAT_CONTRADICTORY_AUTHORITY) == 1


def test_exceptional_game_type_classifies(app):
    p = _pitcher(9)
    _final(708)
    _log(p.id, 708, game_type='S')  # spring training
    s = _run()
    assert _cat(s, audit.CAT_EXCEPTIONAL_GAME_TYPE) == 1


def test_eligible_but_not_selected_is_critical(app):
    p = _pitcher(10)
    _final(709)
    _log(p.id, 709, game_type='R')
    s = _run()
    assert _cat(s, audit.CAT_ELIGIBLE_NOT_SELECTED) == 1
    assert s['exact_backfill_eligible_rows'] == 1
    assert s['result'] == audit.RESULT_FAIL
    assert 'backfill_eligible_rows_remain' in s['decision_reasons']


# ═══════════════ Classification — pure classifier (edge/precedence) ═════════
def _row(game_date=IN_WINDOW, game_pk=999, game_type='R'):
    return SimpleNamespace(id=1, game_date=game_date, mlb_game_pk=game_pk, game_type=game_type)


def test_missing_game_date_classifies():
    cat = audit._classify_row(_row(game_date=None), campaign_start=date(2026, 1, 1),
                              campaign_end=date(2026, 7, 25), schedule_by_pk={}, eligible_pks=set())
    assert cat == audit.CAT_MISSING_GAME_DATE


def test_before_window_classifies():
    cat = audit._classify_row(_row(game_date=date(2025, 12, 31)), campaign_start=date(2026, 1, 1),
                              campaign_end=date(2026, 7, 25), schedule_by_pk={}, eligible_pks=set())
    assert cat == audit.CAT_BEFORE_WINDOW


def test_missing_game_pk_classifies():
    cat = audit._classify_row(_row(game_pk=None), campaign_start=date(2026, 1, 1),
                              campaign_end=date(2026, 7, 25), schedule_by_pk={}, eligible_pks=set())
    assert cat == audit.CAT_MISSING_GAME_PK


def test_other_classified_exclusion_when_final_clean_but_not_eligible():
    sched = [SimpleNamespace(team_id=A, opponent_team_id=B, home_away='home', status_state='final'),
             SimpleNamespace(team_id=B, opponent_team_id=A, home_away='away', status_state='final')]
    cat = audit._classify_row(_row(game_pk=42), campaign_start=date(2026, 1, 1),
                              campaign_end=date(2026, 7, 25), schedule_by_pk={42: sched},
                              eligible_pks=set())  # 42 deliberately absent
    assert cat == audit.CAT_OTHER


def test_precedence_after_cutoff_beats_missing_pk():
    cat = audit._classify_row(_row(game_date=AFTER_CUTOFF, game_pk=None),
                              campaign_start=date(2026, 1, 1), campaign_end=date(2026, 7, 25),
                              schedule_by_pk={}, eligible_pks=set())
    assert cat == audit.CAT_AFTER_CUTOFF


def test_every_row_receives_exactly_one_category(app):
    for i, (pk, mk) in enumerate([(710, lambda pk: _final(pk, AFTER_CUTOFF)),
                                  (711, lambda pk: None),
                                  (712, lambda pk: _sched(pk, [(A, B, 'home', 'scheduled'),
                                                               (B, A, 'away', 'scheduled')]))]):
        p = _pitcher(20 + i)
        mk(pk)
        _log(p.id, pk, game_date=AFTER_CUTOFF if pk == 710 else IN_WINDOW)
    s = _run()
    assert sum(c['row_count'] for c in s['primary_categories'].values()) == s['residual_population']['total_rows']


# ═══════════════ Result contract (unit) ═════════════════════════════════════
def test_result_pass():
    r, reasons = audit._classify_result(total_rows=5, exact_eligible=0, reconcile=True,
                                        invalid=0, unclassified=0, migration_head=None)
    assert r == audit.RESULT_PASS


def test_result_fail_eligible():
    r, reasons = audit._classify_result(total_rows=5, exact_eligible=1, reconcile=True,
                                        invalid=0, unclassified=0, migration_head=None)
    assert r == audit.RESULT_FAIL and 'backfill_eligible_rows_remain' in reasons


def test_result_fail_invalid():
    r, _ = audit._classify_result(total_rows=5, exact_eligible=0, reconcile=True,
                                  invalid=2, unclassified=0, migration_head=None)
    assert r == audit.RESULT_FAIL


def test_result_fail_reconcile():
    r, _ = audit._classify_result(total_rows=5, exact_eligible=0, reconcile=False,
                                  invalid=0, unclassified=0, migration_head=None)
    assert r == audit.RESULT_FAIL


def test_result_fail_migration_mismatch():
    r, reasons = audit._classify_result(total_rows=5, exact_eligible=0, reconcile=True,
                                        invalid=0, unclassified=0, migration_head=['deadbeef'])
    assert r == audit.RESULT_FAIL and 'migration_head_mismatch' in reasons


def test_result_inconclusive_unclassified():
    r, _ = audit._classify_result(total_rows=5, exact_eligible=0, reconcile=True,
                                  invalid=0, unclassified=1, migration_head=None)
    assert r == audit.RESULT_INCONCLUSIVE


def test_result_inconclusive_empty():
    r, _ = audit._classify_result(total_rows=0, exact_eligible=0, reconcile=True,
                                  invalid=0, unclassified=0, migration_head=None)
    assert r == audit.RESULT_INCONCLUSIVE


def test_expected_migration_head_matches_backfill():
    assert audit.EXPECTED_MIGRATION_HEAD == 'a4f1c7e9b3d2'


# ═══════════════ Integrated result / reconciliation ═════════════════════════
def _seed_clean_population(app):
    # Only genuinely-ineligible categories -> exact_eligible == 0.
    p30, p31, p32 = _pitcher(30), _pitcher(31), _pitcher(32)
    _final(720, AFTER_CUTOFF); _log(p30.id, 720, game_date=AFTER_CUTOFF)
    _sched(721, [(A, B, 'home', 'scheduled'), (B, A, 'away', 'scheduled')]); _log(p31.id, 721)
    _sched(722, [(A, B, 'home', 'postponed'), (B, A, 'away', 'postponed')]); _log(p32.id, 722)


def test_clean_population_passes(app):
    _seed_clean_population(app)
    s = _run()
    assert s['result'] == audit.RESULT_PASS
    assert s['exit_code'] == 0
    assert s['exact_backfill_eligible_rows'] == 0
    assert s['unclassified_rows'] == 0
    assert s['category_totals_reconcile'] is True
    assert s['foundation_2_status'] == 'production_complete'


def test_empty_population_inconclusive(app):
    s = _run()
    assert s['result'] == audit.RESULT_INCONCLUSIVE
    assert s['exit_code'] == 2


def test_category_totals_reconcile(app):
    _seed_clean_population(app)
    s = _run()
    assert sum(c['row_count'] for c in s['primary_categories'].values()) == 3
    assert s['residual_population']['total_rows'] == 3


def test_by_month_counts_reconcile(app):
    _seed_clean_population(app)
    s = _run()
    assert sum(s['by_month'].values()) == s['residual_population']['total_rows']


def test_by_game_type_counts_reconcile(app):
    _seed_clean_population(app)
    s = _run()
    assert sum(s['by_game_type'].values()) == s['residual_population']['total_rows']


def test_by_finality_counts_reconcile(app):
    _seed_clean_population(app)
    s = _run()
    assert sum(s['by_finality_state'].values()) == s['residual_population']['total_rows']


def test_population_window_buckets_reconcile(app):
    _seed_clean_population(app)
    s = _run()
    pop = s['residual_population']
    assert (pop['inside_campaign_window'] + pop['before_campaign_window']
            + pop['after_campaign_cutoff'] + pop['missing_game_date']) == pop['total_rows']


def test_schedule_and_context_coverage_present(app):
    p = _pitcher(40)
    _final(730); _log(p.id, 730)
    _context(730, A, B, 'Opp')
    s = _run()
    assert s['schedule_coverage']['rows_with_schedule'] == 1
    assert s['context_coverage']['rows_with_completed_game_context'] == 1


def test_bounded_samples_truncate(app):
    p50, p51 = _pitcher(50), _pitcher(51)
    _final(740, AFTER_CUTOFF); _log(p50.id, 740, game_date=AFTER_CUTOFF)
    _final(741, AFTER_CUTOFF); _log(p51.id, 741, game_date=AFTER_CUTOFF)
    s = _run(row_detail_limit=1, game_detail_limit=1)
    assert len(s['bounded_row_samples']) == 1
    assert len(s['bounded_game_samples']) == 1
    assert s['samples_truncated'] is True


def test_ordering_is_deterministic(app):
    _seed_clean_population(app)
    assert _run() == _run()


# ═══════════════ Foundation 2 query parity ══════════════════════════════════
def test_parity_matches_select_game_keys(app):
    p = _pitcher(60)
    _final(750); _log(p.id, 750)                      # eligible
    _sched(751, [(A, B, 'home', 'scheduled'), (B, A, 'away', 'scheduled')]); _log(_pitcher(61).id, 751)
    keys = backfill._select_game_keys(start_date=date(2026, 1, 1), end_date=date(2026, 7, 25),
                                      after_game_date=None, after_game_pk=None,
                                      batch_size=1000, session=db.session)
    eligible_pks = {pk for _d, pk in keys}
    s = _run()
    assert s['exact_backfill_eligible_rows'] == len(eligible_pks)  # exactly the final/clean game
    assert 750 in eligible_pks and 751 not in eligible_pks


def test_parity_final_no_disqualifier_is_eligible(app):
    _final(752); _log(_pitcher(62).id, 752)
    s = _run()
    assert s['exact_backfill_eligible_rows'] == 1


def test_parity_non_final_not_eligible(app):
    _sched(753, [(A, B, 'home', 'scheduled'), (B, A, 'away', 'scheduled')]); _log(_pitcher(63).id, 753)
    s = _run()
    assert s['exact_backfill_eligible_rows'] == 0


def test_parity_out_of_window_not_eligible(app):
    _final(754, AFTER_CUTOFF); _log(_pitcher(64).id, 754, game_date=AFTER_CUTOFF)
    s = _run()
    assert s['exact_backfill_eligible_rows'] == 0


# ═══════════════ Read-only ══════════════════════════════════════════════════
def test_audit_emits_no_write_sql(app):
    _seed_clean_population(app)
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


def test_audit_reports_database_writes_false(app):
    _seed_clean_population(app)
    s = _run()
    assert s['database_writes_performed'] is False
    assert s['mode'] == 'read_only'


def test_audit_leaves_rows_unmodified(app):
    p = _pitcher(70)
    _final(760); _log(p.id, 760)
    _run()
    row = db.session.query(GameLog).filter_by(mlb_game_pk=760).one()
    assert row.appearance_team_status is None


def test_end_before_start_raises(app):
    with pytest.raises(ValueError):
        _run(campaign_start_date=date(2026, 8, 1), campaign_end_date=date(2026, 1, 1))


# ═══════════════ Report shape / no secrets ══════════════════════════════════
def test_report_has_required_top_level_fields(app):
    _seed_clean_population(app)
    s = _run()
    for key in ('capability', 'mode', 'result', 'exit_code', 'migration_head',
                'expected_migration_head', 'inputs', 'coverage', 'residual_population',
                'primary_categories', 'category_totals_reconcile',
                'exact_backfill_eligible_rows', 'unclassified_rows', 'by_month',
                'by_game_type', 'by_finality_state', 'schedule_coverage',
                'context_coverage', 'bullpen_aggregation_relevance', 'bounded_row_samples',
                'bounded_game_samples', 'samples_truncated', 'decision_reasons',
                'foundation_2_status', 'foundation_3_gate', 'database_writes_performed'):
        assert key in s, key
    assert s['capability'] == 'appearance_team_residual_audit_2026_v1'


def test_report_contains_no_secret_tokens(app):
    _seed_clean_population(app)
    blob = str(_run()).lower()
    for token in ('password', 'secret', 'postgres://', 'authorization', 'statsapi'):
        assert token not in blob


def test_service_never_references_current_team(app):
    lowered = SERVICE_PATH.read_text(encoding='utf-8').lower()
    assert 'pitcher.team_id' not in lowered
    assert 'roster' not in lowered


def test_service_reuses_backfill_selector(app):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'backfill._select_game_keys' in source


# ═══════════════ CLI + workflow contract ════════════════════════════════════
def test_cli_exit_map_and_helpers():
    import argparse
    from scripts import run_2026_residual_audit as cli
    assert cli.CAPABILITY == audit.CAPABILITY
    assert cli._iso_date('2026-04-01') == date(2026, 4, 1)
    with pytest.raises(argparse.ArgumentTypeError):
        cli._iso_date('nope')
    assert cli._bounded_limit('10') == 10
    with pytest.raises(argparse.ArgumentTypeError):
        cli._bounded_limit(str(cli.MAX_DETAIL_LIMIT + 1))


def test_cli_sets_auto_sync_off_and_no_current_team():
    from scripts import run_2026_residual_audit as cli
    source = Path(cli.__file__).read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in source
    assert 'pitcher.team_id' not in source.lower()


def test_workflow_is_dispatch_only():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in source
    for trigger in ('\n  push:', '\n  schedule:', '\n  pull_request:',
                    '\n  workflow_call:', '\n  repository_dispatch:'):
        assert trigger not in source


def test_workflow_has_residual_audit_operation():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'residual_audit' in source
    assert 'run_2026_residual_audit.py' in source
    assert 'appearance-team-residual-audit-2026' in source
    assert 'concurrency:' in source
    assert 'contents: read' in source


def test_workflow_residual_audit_needs_no_confirmation():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    # The apply gate is still guarded by mode == apply, not residual_audit.
    assert "if [ \"$MODE\" = 'apply' ] && [ \"$CONFIRMATION\"" in source


def test_workflow_backfill_summary_uses_proposed_fields():
    source = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert "payload.get('proposed_resolved')" in source
    assert "payload.get('proposed_unresolved')" in source
    assert "payload.get('proposed_conflict')" in source
    assert "payload.get('failed_game_count')" in source
    # The stale keys that displayed None are gone.
    assert "payload.get('appearances_resolved')" not in source
    assert "payload.get('games_failed')" not in source


def test_backfill_write_controls_unchanged(app):
    # The residual audit must not have altered the backfill's apply gates.
    p = _pitcher(80)
    _final(770); _log(p.id, 770)
    summary = backfill.run_backfill(apply=True, confirmation=backfill.CONFIRMATION_PHRASE,
                                    start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                                    client=_NoClient())
    assert summary['result'] == backfill.RESULT_REFUSED  # missing fingerprint still refused


class _NoClient:
    def get_game_boxscore(self, game_pk):
        raise AssertionError('backfill apply gate should refuse before any fetch')
