"""The read-only truth certification harness against a real trusted publication.

A disposable PostgreSQL publication is built through the canonical publisher
(the trusted-publication rehearsal). The harness must certify it without
writing anything, report every domain deterministically, attribute every On
Watch arm to the evidence behind it, and catch planted contradictions between
frozen facts and the canonical rows behind them. The operator script must
refuse to certify when the write probe is accepted, and a certification FAIL
must still be a completed run.
"""

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.roster_status_snapshot import RosterStatusSnapshot
from services import publication_truth_certification as certification
from services import public_serving_authority as psa
from services import tonight_read_model
from services.mlb_club_directory import MLB_CLUBS
from tests.test_trusted_publication_rehearsal import _TonightRehearsal, drop_test_schema
from utils.db import db


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts/certify_publication_truth.py'
SCANNER = SCRIPT_PATH.parent / 'scan_forbidden_artifact_content.py'


def _script():
    spec = importlib.util.spec_from_file_location('certify_publication_truth', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def _rehearsed():
    """One rehearsed trusted publication for the module (it takes ~10s to build).

    Every test's own changes are flushed, never committed, and rolled back by
    ``published``; the publication itself stays as published.
    """
    from api import bullpen as bullpen_api

    patch = pytest.MonkeyPatch()
    # install_public_serving_authority wraps this module attribute process-wide
    # and never unwraps it; register the original so the module leaves it as
    # it found it and a later publication is not wrapped twice.
    patch.setattr(bullpen_api, 'build_bullpen_dashboard_payload',
                  bullpen_api.build_bullpen_dashboard_payload)
    rehearsal = _TonightRehearsal(patch, name='truth certification')
    context = rehearsal.app.app_context()
    context.push()
    try:
        rehearsal.setup()
        snapshot_id = rehearsal.publish('cert_base').id
        yield rehearsal, snapshot_id
    finally:
        db.session.rollback()
        db.session.remove()
        drop_test_schema(rehearsal.app)
        context.pop()
        patch.undo()


@pytest.fixture
def published(_rehearsed):
    rehearsal, snapshot_id = _rehearsed
    db.session.expire_all()
    snapshot = db.session.get(DashboardSnapshot, snapshot_id)
    try:
        yield rehearsal, snapshot
    finally:
        db.session.rollback()
        db.session.expire_all()


def _writes_during(callable_):
    engine = db.session.get_bind()
    statements = []

    def record(_conn, _cursor, statement, *_args):
        verb = statement.lstrip().split(' ', 1)[0].upper()
        if verb in {'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'ALTER', 'DROP', 'CREATE'}:
            statements.append(statement)

    event.listen(engine, 'before_cursor_execute', record)
    try:
        result = callable_()
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    return result, statements


def _scan(directory):
    return subprocess.run(
        [sys.executable, str(SCANNER), '--directory', str(directory)],
        capture_output=True, text=True,
    )


# ── The certification document ──────────────────────────────────────────────

def test_certifies_a_real_publication_without_writing(published):
    _rehearsal, snapshot = published
    report, writes = _writes_during(lambda: certification.certify_snapshot(snapshot))

    assert writes == []
    assert report['contract'] == certification.CERTIFICATION_CONTRACT
    subject = report['subject']
    assert subject['snapshot_id'] == snapshot.id
    assert subject['data_through'] == snapshot.data_through.isoformat()
    assert subject['membership_date'] == snapshot.data_through.isoformat()
    assert subject['availability_date_used'] == (
        snapshot.availability_reference_date.isoformat())
    assert set(report['domains']) == {
        'roster', 'workload', 'team_state', 'schedule', 'tonight'}
    assert set(report['team_verdicts']) == {club.abbreviation for club in MLB_CLUBS}
    assert report['teams_passed'] + report['teams_conditional'] + report[
        'teams_failed'] == 30
    for domain in ('roster', 'workload', 'arm_attribution', 'team_state',
                   'postseason_workload'):
        assert len(report[domain]) == 30, domain
    assert report['tonight'], 'the publication carries a tonight_v1 edition'
    for team in report['team_state'].values():
        assert team['receipt_present'] is True
        assert team['hypothetical']['label'] == 'HYPOTHETICAL / AUDIT ONLY'
        assert team['coverage_at_audit_time'] is not None
    # Every rehearsed reliever pitched relief inside the windows, so the
    # independent recount compared real facts and agreed with all of them.
    assert sum(team['facts_compared'] for team in report['workload'].values()) > 0
    assert report['domains']['workload'] == certification.PASS


def test_the_document_is_deterministic_for_the_same_rows(published):
    _rehearsal, snapshot = published
    first = json.dumps(certification.certify_snapshot(snapshot), sort_keys=True, default=str)
    second = json.dumps(certification.certify_snapshot(snapshot), sort_keys=True, default=str)
    assert first == second


def test_the_league_attribution_sums_the_team_counts(published):
    _rehearsal, snapshot = published
    report = certification.certify_snapshot(snapshot)
    league = report['league_arm_attribution']
    for key, value in league.items():
        assert value == sum(
            team['counts'][key] for team in report['arm_attribution'].values()), key
    for team in report['arm_attribution'].values():
        counts = team['counts']
        assert counts['monitor_total'] == sum(
            counts[basis] for basis in certification.MONITOR_BASES)
        assert counts['active_bullpen_count'] == (
            counts['clean'] + counts['monitor_total'] + counts['limited']
            + counts['avoid'] + counts['unavailable'] + counts['unknown'])


def test_the_records_view_is_the_frozen_publication(published):
    """The attribution reads the frozen records the publication serves."""
    _rehearsal, snapshot = published
    package = snapshot.payload['trusted_team_boards']['by_team_id']
    _team_id, team_package = sorted(package.items())[0]
    assert set(certification._frozen_records(team_package)) == {
        record['pitcher_id'] for record in psa._records_for_view(team_package, False)}


# ── Planted contradictions ──────────────────────────────────────────────────

def _a_quiet_arm(snapshot):
    return next(
        (int(team_id), item)
        for team_id, team_package in sorted(
            snapshot.payload['trusted_team_boards']['by_team_id'].items())
        for item in (team_package.get('recent_usage_rest') or {}).get('active_pitchers') or ()
        if (item.get('pitched_yesterday') or {}).get('status') == 'complete'
        and (item.get('pitched_yesterday') or {}).get('value') is False
    )


def test_a_planted_workload_contradiction_fails_the_team(published):
    _rehearsal, snapshot = published
    baseline = certification.certify_workload(snapshot)
    team_id, arm = _a_quiet_arm(snapshot)
    # A relief appearance yesterday that the frozen facts never saw.
    db.session.add(GameLog(
        pitcher_id=arm['pitcher_id'], mlb_game_pk=99887766,
        game_date=snapshot.data_through, games_started=0, game_type='R',
        innings_pitched=1.0, innings_pitched_outs=3, pitches_thrown=15,
    ))
    db.session.flush()
    planted = certification.certify_workload(snapshot)
    assert baseline[team_id]['verdict'] != certification.FAIL
    assert planted[team_id]['verdict'] == certification.FAIL
    mismatch = next(m for m in planted[team_id]['mismatches']
                    if m['pitcher_id'] == arm['pitcher_id'])
    assert mismatch['diff']['pitched_yesterday'] == {'published': False, 'recount': True}
    assert mismatch['diff']['days_since_last_appearance']['recount'] == 1
    assert 'yesterday.appearances' in mismatch['diff']

    report = certification.certify_snapshot(snapshot)
    assert report['domains']['workload'] == certification.FAIL
    assert any(
        finding['domain'] == 'workload'
        and finding['pitcher_id'] == arm['pitcher_id']
        and 'pitched_yesterday' in finding['facts']
        for finding in report['findings']
    )


def test_a_roster_snapshot_on_another_club_fails_roster(published):
    _rehearsal, snapshot = published
    membership, _availability = certification.reference_dates(snapshot)
    roster = certification.certify_roster(snapshot, membership_date=membership)
    team_id = next(t for t, r in sorted(roster.items()) if r['active_bullpen_count'])
    team_package = snapshot.payload['trusted_team_boards']['by_team_id'][str(team_id)]
    pitcher_id = tonight_read_model._active_arms(team_package)[0]['pitcher_id']
    row = RosterStatusSnapshot.query.filter_by(
        pitcher_id=pitcher_id, snapshot_date=membership).one()
    row.team_id = 999
    db.session.flush()
    after = certification.certify_roster(snapshot, membership_date=membership)
    assert after[team_id]['verdict'] == certification.FAIL
    assert pitcher_id in after[team_id]['wrong_team']
    assert 'roster_snapshot_other_team' in {i['issue'] for i in after[team_id]['issues']}


def test_a_published_arm_listed_by_two_clubs_is_a_duplicate(published, monkeypatch):
    _rehearsal, snapshot = published
    membership, _availability = certification.reference_dates(snapshot)
    by_team = snapshot.payload['trusted_team_boards']['by_team_id']
    first, second = sorted(
        int(t) for t, package in by_team.items() if tonight_read_model._active_arms(package)
    )[:2]
    shared = tonight_read_model._active_arms(by_team[str(first)])[0]
    original = tonight_read_model._active_arms

    def _arms(team_package):
        arms = list(original(team_package))
        if team_package is by_team[str(second)]:
            arms.append(shared)
        return arms

    monkeypatch.setattr(tonight_read_model, '_active_arms', _arms)
    roster = certification.certify_roster(snapshot, membership_date=membership)
    assert shared['pitcher_id'] in roster[first]['duplicate']
    assert shared['pitcher_id'] in roster[second]['duplicate']
    assert shared['pitcher_id'] in roster[second]['extra']
    assert roster[second]['verdict'] == certification.FAIL


# ── Stale vs workload On Watch attribution ──────────────────────────────────

def _plant_monitor(snapshot, team_id, pitcher_id, *, data_state):
    payload = copy.deepcopy(snapshot.payload)
    team = payload['trusted_team_boards']['by_team_id'][str(team_id)]
    for record in team['records']:
        if record.get('pitcher_id') == pitcher_id:
            availability = record['availability']
            availability['availability_status'] = 'Monitor'
            availability['data_state'] = data_state
            availability['confidence'] = 'low' if data_state != 'fresh' else 'high'
    snapshot.payload = payload
    flag_modified(snapshot, 'payload')


def test_stale_and_workload_on_watch_arms_are_attributed_separately(published):
    _rehearsal, snapshot = published
    by_team = snapshot.payload['trusted_team_boards']['by_team_id']
    planted = [
        (int(t), sorted(certification._frozen_records(package))[0])
        for t, package in sorted(by_team.items())
        if certification._frozen_records(package)
    ][:3]
    memberships = {club.team_id: ([], True) for club in MLB_CLUBS}
    for (team_id, pitcher_id), data_state in zip(planted, ('stale', 'missing', 'fresh')):
        memberships[team_id] = ([pitcher_id], True)
        _plant_monitor(snapshot, team_id, pitcher_id, data_state=data_state)
    (stale_team, stale_arm), (missing_team, missing_arm), (work_team, work_arm) = planted

    attribution = certification.certify_arm_attribution(
        snapshot, memberships=memberships, sidecars={}, ledger_complete=True,
    )
    stale = attribution[stale_team]
    assert stale['counts']['monitor_stale'] == 1
    assert stale['counts']['monitor_workload'] == 0
    assert stale['counts']['stale_arms'] == 1
    assert stale['counts']['ledger_confirmed_rest'] == 1
    assert stale['counts']['low_confidence'] == 1
    assert stale['arms'][0]['monitor_basis'] == certification.MONITOR_STALE
    assert stale['arms'][0]['public_form'] == 'On Watch'
    assert stale['population_source'] == 'membership_intersect_frozen_board_records'
    board = stale['board_on_watch_group']
    assert stale_arm in board['pitcher_ids']
    assert board['monitor_stale'] == 1
    assert board['outside_team_state_population'] == 0
    assert board['count'] == sum(board[b] for b in certification.MONITOR_BASES)
    missing = attribution[missing_team]
    assert missing['counts']['monitor_missing'] == 1
    assert missing['counts']['missing_arms'] == 1
    assert missing['counts']['ledger_confirmed_rest'] == 0
    workload = attribution[work_team]
    assert workload['counts']['monitor_workload'] == 1
    assert workload['counts']['monitor_stale'] == 0
    assert workload['arms'][0]['monitor_basis'] == certification.MONITOR_WORKLOAD

    team_state = certification.certify_team_state(
        snapshot, attribution=attribution, sidecars={},
    )
    assert team_state[stale_team]['stale_arms'] == 1
    assert team_state[stale_team]['monitor_from_evidence_quality'] == 1
    assert team_state[stale_team]['partition']['moderate_count'] == 1
    assert team_state[work_team]['monitor_from_evidence_quality'] == 0
    assert team_state[work_team]['monitor_workload'] == 1
    assert team_state[work_team]['hypothetical']['would_differ'] is False
    hypothetical = team_state[stale_team]['hypothetical']
    assert hypothetical['label'] == certification.HYPOTHETICAL_LABEL
    assert hypothetical['evidence_quality_monitor_as_clean'] == (
        certification.contract_a_state(1, 0, 1)[0])
    assert hypothetical['evidence_quality_monitor_excluded'] is None


def test_a_bound_team_state_sidecar_is_the_population(published):
    _rehearsal, snapshot = published
    from services.team_board_delta_substrate import (
        SNAPSHOT_PAYLOAD_VERSION, SNAPSHOT_SOURCE_PREFIX, SNAPSHOT_TYPE,
    )

    by_team = snapshot.payload['trusted_team_boards']['by_team_id']
    team_id, arms = next(
        (int(t), sorted(certification._frozen_records(package)))
        for t, package in sorted(by_team.items())
        if certification._frozen_records(package)
    )
    sidecar_arm = arms[0]
    for source_snapshot_id in (snapshot.id + 1000, snapshot.id):
        db.session.add(DashboardSnapshot(
            snapshot_type=SNAPSHOT_TYPE, source=f'{SNAPSHOT_SOURCE_PREFIX}{team_id}',
            status='ready', is_published=False, payload_version=SNAPSHOT_PAYLOAD_VERSION,
            data_through=snapshot.data_through, published_at=snapshot.published_at,
            payload={
                'team_id': team_id,
                'source': {'snapshot_id': source_snapshot_id},
                'domains': {'team_state': {'trust_state': 'high',
                                           'trust_data_state': 'complete',
                                           'freshness_state': 'current'}},
                'values': {
                    'team_state': {'public_state': 'fresh'},
                    'arm_read': {
                        'member_pitcher_ids': [sidecar_arm],
                        'missing_record_pitcher_ids': [],
                        'records': [{
                            'pitcher_id': sidecar_arm,
                            'public_read': {'key': 'watch_arm'},
                            'evidence_state': {'data_state': 'stale', 'confidence': 'low'},
                        }],
                    },
                },
            },
        ))
    db.session.flush()

    sidecars = certification.team_state_sidecars(snapshot)
    assert set(sidecars) == {team_id}
    assert sidecars[team_id].payload['source']['snapshot_id'] == snapshot.id
    report = certification.certify_snapshot(snapshot, include_audit_time_coverage=False)
    team = report['arm_attribution'][str(team_id)]
    assert team['population_source'] == 'frozen_team_state_sidecar'
    assert [arm['pitcher_id'] for arm in team['arms']] == [sidecar_arm]
    assert team['arms'][0]['sidecar_data_state'] == 'stale'
    assert team['arms'][0]['sidecar_public_read'] == 'watch_arm'
    assert report['team_state'][str(team_id)]['sidecar_bound'] is True
    assert report['team_state'][str(team_id)]['sidecar_trust_state'] == 'high'
    assert report['subject']['team_state_sidecars_bound'] == 1


def test_postseason_relief_work_is_counted_and_never_excluded(published):
    _rehearsal, snapshot = published
    before_report = certification.certify_snapshot(snapshot, include_audit_time_coverage=False)
    team_id, pitcher_id = next(
        (int(t), team['arms'][0]['pitcher_id'])
        for t, team in sorted(before_report['arm_attribution'].items())
        if team['arms']
    )
    db.session.add(GameLog(
        pitcher_id=pitcher_id, mlb_game_pk=99887767,
        game_date=snapshot.data_through, games_started=0, game_type='F',
        innings_pitched=1.0, innings_pitched_outs=3, pitches_thrown=21,
    ))
    db.session.flush()
    report = certification.certify_snapshot(snapshot, include_audit_time_coverage=False)
    before = before_report['postseason_workload'][str(team_id)]['windows']['last_7_days']
    after = report['postseason_workload'][str(team_id)]['windows']['last_7_days']
    assert after['postseason_relief_appearances'] == before['postseason_relief_appearances'] + 1
    assert after['postseason_relief_pitches'] == before['postseason_relief_pitches'] + 21
    assert after['postseason_game_types'] == ['F']
    assert after['relief_appearances'] == before['relief_appearances'] + 1
    assert after['arms_with_postseason_relief'] == 1
    assert report['postseason_workload'][str(team_id)]['postseason_workload_present'] is True
    assert any(f['issue'] == 'postseason_relief_work_in_workload_windows'
               and f['team'] == report['postseason_workload'][str(team_id)]['team']
               for f in report['findings'])


# ── Contract A on counts (audit-only) ───────────────────────────────────────

@pytest.mark.parametrize('clean,severe,total,state', [
    (2, 0, 10, 'vulnerable'),      # margin floor
    (5, 3, 9, 'vulnerable'),       # severity share 1/3
    (6, 1, 10, 'fresh'),           # 3/5 clean, >= 5 clean, <= 1 severe
    (5, 2, 8, 'stretched'),        # two severe arms
    (5, 0, 9, 'stretched'),        # clean share below 3/5
    (0, 0, 0, None),
])
def test_contract_a_on_counts(clean, severe, total, state):
    assert certification.contract_a_state(clean, severe, total)[0] == state


@pytest.mark.parametrize('availability,basis', [
    ({'data_state': 'fresh'}, certification.MONITOR_WORKLOAD),
    ({'data_state': 'stale'}, certification.MONITOR_STALE),
    ({'data_state': 'missing'}, certification.MONITOR_MISSING),
    ({'data_state': 'incomplete', 'inputs': {'workload_fetch_failed': True}},
     certification.MONITOR_FETCH_FAILURE),
    ({'data_state': 'incomplete'}, certification.MONITOR_INCOMPLETE),
    ({'data_state': None}, certification.MONITOR_OTHER),
])
def test_monitor_basis(availability, basis):
    assert certification.monitor_basis(availability) == basis


# ── Operator script ─────────────────────────────────────────────────────────

def test_loading_the_script_has_no_process_side_effects(monkeypatch):
    monkeypatch.delenv('PGOPTIONS', raising=False)
    monkeypatch.delenv('AUTO_SYNC', raising=False)
    monkeypatch.delitem(sys.modules, 'app', raising=False)
    _script()
    assert 'PGOPTIONS' not in os.environ
    assert 'AUTO_SYNC' not in os.environ
    assert 'app' not in sys.modules


def test_the_read_only_option_is_applied_once_when_the_script_runs(monkeypatch):
    monkeypatch.setenv('PGOPTIONS', '-c statement_timeout=0')
    monkeypatch.setenv('AUTO_SYNC', 'true')
    script = _script()
    script._configure_read_only_process()
    script._configure_read_only_process()
    assert os.environ['PGOPTIONS'] == (
        '-c statement_timeout=0 -c default_transaction_read_only=on')
    assert os.environ['AUTO_SYNC'] == 'false'


@pytest.mark.parametrize('argv', [
    [],
    ['--snapshot-id', '0'],
    ['--snapshot-id', '-4496'],
    ['--snapshot-id', '44x96'],
    ['--snapshot-id', '4496; rm -rf /'],
    ['--snapshot-id', '$(id)'],
    ['--snapshot-id', ''],
])
def test_invalid_snapshot_ids_are_rejected_by_the_parser(argv):
    with pytest.raises(SystemExit) as refused:
        _script()._parse_args(argv)
    assert refused.value.code == 2


def _main(script, published, monkeypatch, argv):
    """Run the operator command with its process settings scoped to the test.

    ``main`` sets PGOPTIONS (read-only) and AUTO_SYNC for its own process, as an
    operator command should. Inside the test process those settings must not
    outlive the test, or every later connection in the run starts read-only.
    """
    rehearsal, _snapshot = published
    for key in ('PGOPTIONS', 'AUTO_SYNC'):
        # setenv records the prior value (or its absence) so undo restores it;
        # delenv of an absent key records nothing and would leak.
        monkeypatch.setenv(key, os.environ.get(key, ''))
    monkeypatch.setattr(script, 'build_app', lambda: rehearsal.app)
    try:
        return script.main(argv)
    finally:
        # Connections opened while PGOPTIONS was read-only stay read-only;
        # never hand them to a later test.
        db.session.remove()
        db.session.get_bind().dispose()


def test_running_the_command_in_a_test_does_not_leak_read_only_settings(
    published, monkeypatch, tmp_path,
):
    _rehearsal, snapshot = published
    before = {key: os.environ.get(key) for key in ('PGOPTIONS', 'AUTO_SYNC')}
    with monkeypatch.context() as scoped:
        code = _main(_script(), published, scoped,
                     ['--snapshot-id', str(snapshot.id), '--output-dir', str(tmp_path)])
        assert 'default_transaction_read_only=on' in os.environ['PGOPTIONS']
    assert code == 0
    assert {key: os.environ.get(key) for key in ('PGOPTIONS', 'AUTO_SYNC')} == before


def test_the_script_certifies_read_only_and_a_fail_is_a_completed_run(
    published, monkeypatch, tmp_path,
):
    _rehearsal, snapshot = published
    script = _script()
    output = tmp_path / 'out'
    code = _main(script, published, monkeypatch,
                 ['--snapshot-id', str(snapshot.id), '--output-dir', str(output)])
    assert code == script.EXIT_OK
    assert sorted(p.name for p in output.iterdir()) == [
        f'certification-{snapshot.id}.json', f'certification-{snapshot.id}.md']
    document = json.loads((output / f'certification-{snapshot.id}.json').read_text())
    assert document['mode'] == 'certified'
    assert document['read_only_proof']['read_only_probe_refused'] is True
    assert document['read_only_proof']['durable_write_attempts'] == 0
    # The rehearsal's synthesized Team State receipts do not reproduce from the
    # partition, so this certification is not PASS; the run still completed.
    assert document['certification']['league_verdict'] != certification.PASS
    markdown = (output / f'certification-{snapshot.id}.md').read_text()
    assert markdown.startswith('# Publication truth certification')
    assert 'HYPOTHETICAL / AUDIT ONLY' in markdown
    assert _scan(output).returncode == 0


def test_an_accepted_write_probe_certifies_nothing(published, monkeypatch, tmp_path):
    _rehearsal, snapshot = published
    script = _script()
    original_execute = db.session.execute

    def _execute(statement, *args, **kwargs):
        if 'SET TRANSACTION READ ONLY' in str(getattr(statement, 'text', statement)):
            return None
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db.session, 'execute', _execute)
    certified = []
    monkeypatch.setattr(certification, 'certify_snapshot',
                        lambda *a, **k: certified.append(a) or {})
    output = tmp_path / 'out'
    code = _main(script, published, monkeypatch,
                 ['--snapshot-id', str(snapshot.id), '--output-dir', str(output)])
    assert code == script.EXIT_READ_ONLY_UNPROVEN
    assert certified == []
    assert sorted(p.name for p in output.iterdir()) == [
        'certification-refused.json', 'certification-refused.md']
    refusal = json.loads((output / 'certification-refused.json').read_text())
    assert refusal['reason_code'] == 'read_only_unproven'
    assert refusal['read_only_proof']['read_only_probe_refused'] is False
    assert refusal['read_only_proof']['durable_write_attempts'] == 0
    assert _scan(output).returncode == 0


@pytest.mark.parametrize('case', ['missing', 'not_trusted'])
def test_an_unknown_or_untrusted_snapshot_is_refused(published, monkeypatch, tmp_path, case):
    _rehearsal, snapshot = published
    script = _script()
    target_id = snapshot.id + 100000
    if case == 'not_trusted':
        row = DashboardSnapshot(
            snapshot_type='team_board_delta', source='tb_delta:team:147', status='ready',
            is_published=False, payload_version=1, data_through=snapshot.data_through,
            payload={'team_id': 147},
        )
        db.session.add(row)
        db.session.commit()
        target_id = row.id
        cleanup = row
    else:
        cleanup = None
    output = tmp_path / 'out'
    try:
        code = _main(script, published, monkeypatch,
                     ['--snapshot-id', str(target_id), '--output-dir', str(output)])
    finally:
        if cleanup is not None:
            db.session.delete(cleanup)
            db.session.commit()
    assert code == script.EXIT_REFUSED
    refusal = json.loads((output / 'certification-refused.json').read_text())
    assert refusal['reason_code'] == (
        'snapshot_not_found' if case == 'missing' else 'snapshot_not_trusted_publication')
    assert not (output / f'certification-{target_id}.json').exists()
    assert _scan(output).returncode == 0


def test_a_certification_error_is_an_operational_failure(published, monkeypatch, tmp_path):
    _rehearsal, snapshot = published
    script = _script()

    def _boom(*_args, **_kwargs):
        raise RuntimeError('certification broke')

    monkeypatch.setattr(certification, 'certify_snapshot', _boom)
    output = tmp_path / 'out'
    with pytest.raises(RuntimeError):
        _main(script, published, monkeypatch,
              ['--snapshot-id', str(snapshot.id), '--output-dir', str(output)])
    assert not output.exists() or not any(output.iterdir())
