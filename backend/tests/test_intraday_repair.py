from contextlib import nullcontext
from types import SimpleNamespace

from services import intraday_reconcile
from services import intraday_repair
from services.intraday_repair import build_roster_repair_scope


def _audit(*differences, status='success', verification='complete'):
    return {
        'status': status,
        'lanes': {
            intraday_reconcile.LANE_ROSTER_ASSIGNMENT: {
                'verification_status': verification,
                'differences': list(differences),
            }
        },
    }


def _finding(change_type, *, stored_pitcher_id=11, mlb_player_id=101,
             stored_team_id=143, observed_team_id=143, severity='actionable'):
    return {
        'change_type': change_type,
        'stored_pitcher_id': stored_pitcher_id,
        'mlb_player_id': mlb_player_id,
        'stored_team_id': stored_team_id,
        'observed_official_team_id': observed_team_id,
        'severity': severity,
        'bullpen_population_effect': intraday_reconcile.EFFECT_ENTER,
    }


def test_no_change_is_safe_noop():
    scope = build_roster_repair_scope(_audit())
    assert scope['status'] == 'no_change'
    assert scope['affected_team_ids'] == []


def test_existing_recall_is_repairable():
    scope = build_roster_repair_scope(_audit(
        _finding(intraday_reconcile.CHANGE_RECALL)
    ))
    assert scope['status'] == 'ready'
    assert scope['affected_team_ids'] == [143]
    assert scope['affected_pitcher_ids'] == [11]
    assert scope['affected_pitcher_mlb_ids'] == [101]


def test_existing_active_roster_departure_is_repairable():
    finding = _finding(
        intraday_reconcile.CHANGE_REMOVED_FROM_ACTIVE_ROSTER,
        severity='actionable',
    )
    finding['bullpen_population_effect'] = intraday_reconcile.EFFECT_LEAVE
    scope = build_roster_repair_scope(_audit(finding))
    assert scope['status'] == 'ready'
    assert scope['repairable_findings'] == [finding]
    assert scope['roster_status_findings'] == [finding]
    assert scope['identity_findings'] == []


def test_newly_discovered_player_is_routed_to_identity_repair():
    recall = _finding(intraday_reconcile.CHANGE_RECALL)
    newly_discovered = _finding(
        intraday_reconcile.CHANGE_NEWLY_DISCOVERED_ACTIVE,
        stored_pitcher_id=None,
        mlb_player_id=777,
    )
    scope = build_roster_repair_scope(_audit(recall, newly_discovered))
    assert scope['status'] == 'ready'
    assert scope['reason'] is None
    assert scope['repairable_findings'] == [recall, newly_discovered]
    assert scope['roster_status_findings'] == [recall]
    assert scope['identity_findings'] == [newly_discovered]
    assert scope['unsupported_findings'] == []
    assert scope['affected_team_ids'] == [143]
    assert scope['affected_pitcher_ids'] == [11]
    assert scope['affected_pitcher_mlb_ids'] == [101, 777]


def test_team_assignment_change_is_routed_to_identity_repair():
    finding = _finding(
        intraday_reconcile.CHANGE_TEAM_ASSIGNMENT_CHANGE,
        stored_team_id=121,
        observed_team_id=143,
    )
    scope = build_roster_repair_scope(_audit(finding))
    assert scope['status'] == 'ready'
    assert scope['reason'] is None
    assert scope['repairable_findings'] == [finding]
    assert scope['roster_status_findings'] == []
    assert scope['identity_findings'] == [finding]
    assert scope['unsupported_findings'] == []
    assert scope['affected_team_ids'] == [121, 143]
    assert scope['affected_pitcher_ids'] == [11]
    assert scope['affected_pitcher_mlb_ids'] == [101]


def test_partial_roster_lane_blocks_all_writes():
    scope = build_roster_repair_scope(_audit(
        _finding(intraday_reconcile.CHANGE_RECALL),
        verification='partial',
    ))
    assert scope['status'] == 'blocked'
    assert scope['reason'] == 'roster_lane_not_complete'
    assert scope['repairable_findings'] == []


def test_failed_audit_blocks_all_writes():
    scope = build_roster_repair_scope(_audit(
        _finding(intraday_reconcile.CHANGE_RECALL),
        status='failed',
    ))
    assert scope['status'] == 'blocked'
    assert scope['reason'] == 'audit_not_successful'


def _fake_app():
    return SimpleNamespace(app_context=lambda: nullcontext())


def _wire_sync_metadata(monkeypatch):
    guard = SimpleNamespace(release=lambda: None)
    monkeypatch.setattr(
        intraday_repair.sync_metadata,
        'acquire_sync_writer_guard',
        lambda **_kwargs: guard,
    )
    monkeypatch.setattr(
        intraday_repair.sync_metadata, 'start_sync_run', lambda **_kwargs: 91
    )
    monkeypatch.setattr(
        intraday_repair.sync_metadata, 'set_sync_stage', lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        intraday_repair.sync_metadata,
        'finish_sync_run',
        lambda sync_run_id, **_kwargs: SimpleNamespace(id=sync_run_id),
    )
    monkeypatch.setattr(intraday_repair.db.session, 'commit', lambda: None)
    monkeypatch.setattr(intraday_repair.db.session, 'rollback', lambda: None)


def test_transaction_repair_executes_before_no_change_exit(monkeypatch):
    _wire_sync_metadata(monkeypatch)
    calls = []

    result = intraday_repair.run_intraday_roster_repair(
        _fake_app(),
        audit_runner=lambda **_kwargs: _audit(),
        repair_transaction_roster_evidence=True,
        transaction_roster_repair=lambda **_kwargs: calls.append('transaction') or {
            'status': 'success',
            'repair_candidates': 1,
            'roster_gets_attempted': 4,
            'transactions_corrected': 0,
        },
    )

    assert calls == ['transaction']
    assert result['status'] == 'success'
    assert result['transaction_roster_repair']['repair_candidates'] == 1
    assert result['dashboard_snapshot_id'] is None
    assert 'no publishable intraday changes' in result['message']


def test_disabled_transaction_repair_preserves_ordinary_no_change(monkeypatch):
    called = []
    monkeypatch.setattr(
        intraday_repair.sync_metadata,
        'acquire_sync_writer_guard',
        lambda **_kwargs: called.append('writer'),
    )
    monkeypatch.setattr(
        intraday_repair.sync_metadata,
        'start_sync_run',
        lambda **_kwargs: called.append('run_started') or 91,
    )
    monkeypatch.setattr(
        intraday_repair.sync_metadata,
        'finish_sync_run',
        lambda sync_run_id, **_kwargs: (
            called.append(('run_finished', sync_run_id, _kwargs))
            or SimpleNamespace(id=sync_run_id)
        ),
    )

    result = intraday_repair.run_intraday_roster_repair(
        _fake_app(),
        audit_runner=lambda **_kwargs: _audit(),
        repair_transaction_roster_evidence=False,
        transaction_roster_repair=lambda **_kwargs: called.append('transaction'),
    )

    assert result['status'] == 'success'
    assert result['transaction_roster_repair'] is None
    assert called[0] == 'run_started'
    assert called[1][0:2] == ('run_finished', 91)
    assert called[1][2]['canonical_mutations'] == 0
    assert 'writer' not in called


def test_transaction_correction_survives_roster_no_change_and_publishes(monkeypatch):
    _wire_sync_metadata(monkeypatch)
    calls = []

    result = intraday_repair.run_intraday_roster_repair(
        _fake_app(),
        audit_runner=lambda **_kwargs: _audit(),
        repair_transaction_roster_evidence=True,
        transaction_roster_repair=lambda **_kwargs: calls.append('transaction') or {
            'status': 'success',
            'repair_candidates': 1,
            'roster_gets_attempted': 4,
            'transactions_corrected': 1,
        },
        identity_repair=lambda _findings: calls.append('identity'),
        roster_sync=lambda **_kwargs: calls.append('roster'),
        recent_log_sync=lambda **_kwargs: calls.append('logs') or {
            'errors': 0, 'records_failed': 0, 'new_logs_added': 0,
            'logs_corrected': 0,
        },
        fatigue_recalc=lambda **_kwargs: calls.append('fatigue') or 0,
        today_builder=lambda *_args, **_kwargs: {'status': 'ok', 'snapshot_id': 1},
        tonight_builder=lambda *_args, **_kwargs: {'status': 'ok', 'snapshot_id': 2},
        complete_with_snapshot=lambda *_args, **_kwargs: (
            SimpleNamespace(id=91), SimpleNamespace(id=92)
        ),
        publication_proof_builder=lambda *_args, **_kwargs: {'verified': True},
    )

    assert result['status'] == 'success'
    assert result['dashboard_snapshot_id'] == 92
    assert calls == ['transaction', 'logs', 'fatigue']


def test_enabled_transaction_repair_failure_is_visible(monkeypatch):
    _wire_sync_metadata(monkeypatch)
    result = intraday_repair.run_intraday_roster_repair(
        _fake_app(),
        audit_runner=lambda **_kwargs: _audit(),
        repair_transaction_roster_evidence=True,
        transaction_roster_repair=lambda **_kwargs: {
            'status': 'failed',
            'fetch_failures': 4,
            'transactions_corrected': 0,
        },
    )

    assert result['status'] == 'failed'
    assert result['transaction_roster_repair']['fetch_failures'] == 4
    assert 'incomplete' in result['error']
