"""The Team State coverage diagnostic explains the proof's verdict, arm by arm.

Daily Primary SyncRun 93108 withheld candidate 4132 with
``snapshot_team_state_ineligible:118:data_state:incomplete,confidence:low,
status_code_unsupported:data_limited``. The proof kept only those reason codes,
so which of team 118's active-bullpen arms were unusable, and why, could not be
recovered from the run.

The fixture is a synthetic team 118 with one active-bullpen arm per cause. The
diagnostic must reach exactly the verdict the production classifier reaches on
the same records, and name each arm's cause.
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime

import pytest

from api import team_operations
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_failure import SyncFailure
from services import active_bullpen_coverage_diagnostic as diagnostic
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from tests.test_slate_coverage import app  # noqa: F401
from utils.db import db


TEAM = 118
MEMBERSHIP_DATE = date(2026, 9, 29)
AVAILABILITY_DATE = date(2026, 9, 30)
SCORED_AT = datetime(2026, 9, 30, 10, 20)


def _pitcher(mlb_id, name, *, team_id=TEAM, active=True):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=name, team_id=team_id, active=active,
        team_abbreviation='KC' if team_id == TEAM else 'NYY', position='P',
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _score(pitcher, calculated_at=SCORED_AT):
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, calculated_at=calculated_at, raw_score=20.0,
        risk_level='LOW',
    ))


def _log(pitcher, game_date, game_pk, pitches=18):
    db.session.add(GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=game_date,
        innings_pitched=1.0, innings_pitched_outs=3, pitches_thrown=pitches,
    ))


@pytest.fixture
def team_118(app, monkeypatch):  # noqa: F811
    with app.app_context():
        arms = {}
        for index, name in enumerate(('fresh_a', 'fresh_b', 'fresh_c')):
            arms[name] = _pitcher(700 + index, name)
            _score(arms[name])
            _log(arms[name], date(2026, 9, 26), 9100 + index)
        arms['rested'] = _pitcher(710, 'rested')
        _score(arms['rested'], datetime(2026, 9, 2, 10, 0))
        _log(arms['rested'], date(2026, 9, 1), 9110)
        arms['fetch_failed'] = _pitcher(711, 'fetch_failed')
        _score(arms['fetch_failed'])
        _log(arms['fetch_failed'], date(2026, 9, 26), 9111)
        db.session.add(SyncFailure(
            job_name='daily_sync', entity_type='pitcher_game_logs', entity_ref='711',
            error='ReadTimeout', resolved=False, created_at=datetime(2026, 9, 12, 10, 9),
        ))
        arms['never_scored'] = _pitcher(712, 'never_scored')
        arms['other_team'] = _pitcher(713, 'other_team', team_id=147)
        _score(arms['other_team'])
        arms['incomplete_log'] = _pitcher(714, 'incomplete_log')
        _score(arms['incomplete_log'])
        _log(arms['incomplete_log'], date(2026, 9, 27), 9114, pitches=None)
        arms['no_history'] = _pitcher(715, 'no_history')
        _score(arms['no_history'])
        db.session.commit()

        member_ids = frozenset(pitcher.id for pitcher in arms.values())
        monkeypatch.setattr(
            diagnostic, 'resolve_active_bullpen_membership',
            lambda team_id, reference_date: (
                (member_ids, True) if (team_id, reference_date) == (TEAM, MEMBERSHIP_DATE)
                else (frozenset(), False)
            ),
        )
        monkeypatch.setattr(team_operations, '_appearance_ledger_complete', lambda _ref: True)
        yield {name: pitcher.id for name, pitcher in arms.items()}, member_ids


def _diagnose():
    return diagnostic.diagnose_active_bullpen_coverage(
        TEAM, membership_date=MEMBERSHIP_DATE, availability_date=AVAILABILITY_DATE,
    )


def test_every_active_arm_is_named_with_its_first_unusable_cause(app, team_118):
    ids, _members = team_118
    with app.app_context():
        report = _diagnose()

    causes = {arm['pitcher_id']: arm['cause'] for arm in report['arms']}
    assert causes == {
        ids['fresh_a']: 'usable_fresh',
        ids['fresh_b']: 'usable_fresh',
        ids['fresh_c']: 'usable_fresh',
        ids['rested']: 'usable_ledger_rest',
        ids['fetch_failed']: 'unresolved_fetch_failure',
        ids['never_scored']: 'no_record_never_scored',
        ids['other_team']: 'no_record_other_team',
        ids['incomplete_log']: 'unresolved_incomplete_log',
        ids['no_history']: 'unresolved_missing_history',
    }
    fetch_failed = next(a for a in report['arms'] if a['pitcher_id'] == ids['fetch_failed'])
    assert fetch_failed['open_fetch_failures'][0]['created_at'] == '2026-09-12T10:09:00'
    assert fetch_failed['open_fetch_failures'][0]['job_name'] == 'daily_sync'
    other = next(a for a in report['arms'] if a['pitcher_id'] == ids['other_team'])
    assert other['pitcher_team_id'] == 147


def test_the_verdict_is_the_production_triple(app, team_118):
    with app.app_context():
        report = _diagnose()
    assert (report['active_bullpen_count'], report['usable_record_count'],
            report['unresolved_record_count']) == (9, 4, 5)
    assert (report['confidence'], report['data_state']) == ('low', 'incomplete')
    assert report['coverage_reason_code'] == 'insufficient_active_bullpen_coverage'


def test_the_diagnostic_agrees_with_the_production_classifier(app, team_118):
    """Parity: the explanation must never disagree with the verdict it explains."""
    _ids, member_ids = team_118
    with app.app_context():
        report = _diagnose()
        records = classify_latest_fatigue_rows(
            latest_fatigue_rows(team_id=TEAM, limit=team_operations.TEAM_OPERATIONS_DEFAULT_LIMIT),
            reference_date=AVAILABILITY_DATE, mode=CURRENT_AVAILABILITY_MODE,
        )
        production = team_operations._assess_active_bullpen_coverage(
            records, sync_status={'freshness': {'is_current': True}},
            team_id=TEAM, reference_date=AVAILABILITY_DATE,
            membership=(member_ids, True),
        )

    assert (production.confidence, production.data_state) == (
        report['confidence'], report['data_state'],
    )
    assert (production.active_bullpen_count, production.usable_record_count,
            production.unresolved_record_count) == (
        report['active_bullpen_count'], report['usable_record_count'],
        report['unresolved_record_count'],
    )


def test_an_incomplete_ledger_turns_rest_into_unproven_rest(app, team_118):
    ids, _members = team_118
    with app.app_context():
        report = diagnostic.diagnose_active_bullpen_coverage(
            TEAM, membership_date=MEMBERSHIP_DATE, availability_date=AVAILABILITY_DATE,
            ledger_complete=False,
        )
    rested = next(a for a in report['arms'] if a['pitcher_id'] == ids['rested'])
    assert rested['cause'] == 'unresolved_rest_unproven'


def test_a_missing_roster_authority_is_reported_as_unknown_not_low(app, team_118):
    with app.app_context():
        report = diagnostic.diagnose_active_bullpen_coverage(
            TEAM, membership_date=AVAILABILITY_DATE, availability_date=AVAILABILITY_DATE,
        )
    assert report['authority_complete'] is False
    assert report['arms'] == []
    assert (report['confidence'], report['data_state']) == ('unknown', 'missing')


def test_the_diagnostic_writes_nothing(app, team_118):
    with app.app_context():
        before = {
            model.__tablename__: model.query.count()
            for model in (Pitcher, FatigueScore, GameLog, SyncFailure)
        }
        _diagnose()
        after = {
            model.__tablename__: model.query.count()
            for model in (Pitcher, FatigueScore, GameLog, SyncFailure)
        }
        assert not db.session.new and not db.session.dirty and not db.session.deleted
    assert before == after


@pytest.mark.parametrize('active,usable,headroom', [
    (9, 9, 2),    # complete; two arms may still turn unresolved
    (8, 6, 0),    # exactly on the medium bar
    (8, 5, -1),   # below six usable
    (12, 9, -1),  # three unresolved
    (10, 8, 0),   # 80%; one more flip breaks 75%
    (9, 4, -3),   # the fixture's team 118
])
def test_unresolved_headroom_mirrors_the_medium_thresholds(active, usable, headroom):
    assert diagnostic.unresolved_headroom(active, usable) == headroom


def test_each_arm_carries_the_inputs_the_classifier_read(app, team_118):
    ids, _members = team_118
    with app.app_context():
        report = _diagnose()
    arms = {arm['pitcher_id']: arm for arm in report['arms']}

    fresh = arms[ids['fresh_a']]
    assert fresh['readiness_record_exists'] is True
    assert fresh['fatigue_calculated_at'] == '2026-09-30T10:20:00'
    assert fresh['record_data_state'] == 'fresh'
    assert fresh['latest_game_log_date'] == '2026-09-26'
    assert fresh['days_since_last_appearance'] == 4
    assert (fresh['window_log_count'], fresh['window_logs_missing_pitch_count']) == (1, 0)

    incomplete = arms[ids['incomplete_log']]
    assert incomplete['window_logs_missing_pitch_count'] == 1
    never = arms[ids['never_scored']]
    assert never['readiness_record_exists'] is False
    assert never['latest_game_log_date'] is None
    assert never['days_since_last_appearance'] is None

    assert report['coverage_pct'] == 44.4
    assert report['unresolved_headroom'] == -3
    assert report['eligible_coverage'] is False
    assert report['medium_bar'] == {
        'min_usable': 6, 'max_unresolved': 2, 'min_coverage_pct': 75.0,
    }


def test_league_rows_are_ordered_by_headroom_and_flag_the_margin(app, team_118):
    with app.app_context():
        league = diagnostic.diagnose_league(
            [147, TEAM], membership_date=MEMBERSHIP_DATE, availability_date=AVAILABILITY_DATE,
        )
    rows = {row['team_id']: row for row in league['teams']}
    assert rows[TEAM]['team'] == 'KC'
    assert rows[TEAM]['eligible_coverage'] is False
    # No roster authority for 147 in this fixture: unknown, and the least headroom.
    assert rows[147]['confidence'] == 'unknown'
    assert [row['team_id'] for row in league['teams']] == [147, TEAM]
    assert set(league['ineligible_team_ids']) == {147, TEAM}
    assert set(league) >= {'one_arm_from_failing', 'two_arms_from_failing'}


# ── Operator script: structured output and refusals ─────────────────────────

import importlib.util  # noqa: E402
from pathlib import Path  # noqa: E402

_SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/diagnose_team_state_coverage.py'


def _script():
    spec = importlib.util.spec_from_file_location('diagnose_team_state_coverage', _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_files_are_named_for_the_scope_and_snapshot():
    script = _script()
    assert script.output_basename(snapshot_id=4132, team_id=118) == (
        'team-state-coverage-team-118-snapshot-4132'
    )
    assert script.output_basename(snapshot_id=4132, league=True) == (
        'team-state-coverage-league-snapshot-4132'
    )


def test_a_non_mlb_team_is_refused_before_any_database_access(monkeypatch):
    script = _script()
    monkeypatch.delitem(sys.modules, 'app', raising=False)
    assert script.main(['--snapshot-id', '4132', '--team-id', '999']) == script.EXIT_REFUSED
    assert 'app' not in sys.modules


@pytest.mark.parametrize('argv', [
    ['--snapshot-id', '4132', '--team-id', '118', '--league'],
    ['--snapshot-id', '0', '--team-id', '118'],
    ['--snapshot-id', '4132', '--team-id', '-1'],
    ['--snapshot-id', '4132'],
])
def test_invalid_scope_arguments_are_rejected(argv):
    with pytest.raises(SystemExit) as refused:
        _script()._parse_args(argv)
    assert refused.value.code == 2


def test_the_written_evidence_is_complete_and_scan_safe(app, team_118, tmp_path):
    script = _script()
    with app.app_context():
        report = _diagnose()
    document = {
        'diagnostic': 'team_state_active_bullpen_coverage',
        'schema_version': script.SCHEMA_VERSION,
        'mode': 'team',
        'snapshot': {'snapshot_id': 4132},
        'read_only_proof': {'read_only_probe_refused': True},
        'run': {'commit_sha': None, 'workflow_run_id': None},
        'non_authorization_statement': script.NON_AUTHORIZATION_STATEMENT,
        'report': report,
    }
    path = script._write_outputs(
        document, tmp_path, script.output_basename(snapshot_id=4132, team_id=118),
    )
    written = json.loads(path.read_text())
    assert written['report']['arms'] == json.loads(json.dumps(report['arms'], default=str))
    summary = (tmp_path / 'team-state-coverage-team-118-snapshot-4132.md').read_text()
    assert 'Team 118: 4 of 9 active relievers usable' in summary
    assert 'unresolved_fetch_failure' in summary

    scanner = subprocess.run(
        [sys.executable, str(_SCRIPT.parent / 'scan_forbidden_artifact_content.py'),
         '--directory', str(tmp_path)],
        capture_output=True, text=True,
    )
    assert scanner.returncode == 0, scanner.stdout + scanner.stderr


def test_stored_failure_text_is_reduced_to_a_safe_label():
    label = diagnostic._safe_error_label(
        'MLB API fetch failed for /people/1/stats: ReadTimeout host=statsapi token=abc\n'
        'Traceback (most recent call last): ...'
    )
    assert label == 'MLB API fetch failed for /people/1/stats'
    assert diagnostic._safe_error_label(
        'connect postgresql://u:p@h/db failed'
    ) == 'connect [url] failed'
    assert diagnostic._safe_error_label('retry key=value') == 'retry [redacted]'
    assert diagnostic._safe_error_label(None) == ''


def test_loading_the_script_does_not_change_the_process_environment(monkeypatch):
    monkeypatch.delenv('PGOPTIONS', raising=False)
    _script()
    assert 'PGOPTIONS' not in os.environ


def test_the_read_only_option_is_applied_once_when_the_script_runs(monkeypatch):
    monkeypatch.setenv('PGOPTIONS', '-c statement_timeout=0')
    monkeypatch.setenv('AUTO_SYNC', 'false')
    script = _script()
    script._configure_read_only_process()
    script._configure_read_only_process()
    assert os.environ['PGOPTIONS'] == (
        '-c statement_timeout=0 -c default_transaction_read_only=on'
    )


# ── Refusal evidence and explicit-date anchoring ────────────────────────────

def test_explicit_date_outputs_are_named_for_their_dates():
    assert _script().output_basename(
        snapshot_id=None, team_id=118,
        membership_date='2026-09-29', availability_date='2026-09-30',
    ) == 'team-state-coverage-team-118-dates-2026-09-29-2026-09-30'


@pytest.mark.parametrize('argv,reason', [
    (['--snapshot-id', '4132', '--team-id', '999'], 'team_not_mlb_club'),
    (['--team-id', '118'], 'reference_dates_missing'),
    (['--team-id', '118', '--membership-date', '2026-09-29'], 'reference_dates_missing'),
])
def test_a_refusal_before_database_access_leaves_a_scan_safe_document(
    tmp_path, monkeypatch, argv, reason,
):
    script = _script()
    monkeypatch.delitem(sys.modules, 'app', raising=False)
    code = script.main([*argv, '--output-dir', str(tmp_path)])
    assert code == script.EXIT_REFUSED
    assert 'app' not in sys.modules
    refusal = json.loads((tmp_path / 'team-state-coverage-refused.json').read_text())
    assert refusal['mode'] == 'refused'
    assert refusal['reason_code'] == reason
    assert refusal['exit_code'] == 2
    assert (tmp_path / 'team-state-coverage-refused.md').read_text().startswith(
        '# Team State coverage diagnostic: refused'
    )
    scanner = subprocess.run(
        [sys.executable, str(_SCRIPT.parent / 'scan_forbidden_artifact_content.py'),
         '--directory', str(tmp_path)],
        capture_output=True, text=True,
    )
    assert scanner.returncode == 0, scanner.stdout + scanner.stderr


def test_a_malformed_date_is_rejected_by_the_argument_parser():
    with pytest.raises(SystemExit) as refused:
        _script()._parse_args(['--team-id', '118', '--membership-date', '09/29/2026',
                               '--availability-date', '2026-09-30'])
    assert refused.value.code == 2


def test_the_snapshot_not_found_guidance_names_the_explicit_date_anchor():
    guidance = _script().SNAPSHOT_NOT_FOUND_GUIDANCE
    assert 'rolled back' in guidance
    assert '--membership-date' in guidance and '--availability-date' in guidance
