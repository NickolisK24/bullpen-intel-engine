from services import intraday_reconcile
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
