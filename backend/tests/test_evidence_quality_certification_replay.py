"""Snapshot-4496 topology replay through the real publisher and the certification harness.

The governed certification of snapshot 4496 proved P1-1 on WSH, COL, TEX, MIN,
MIA, AZ and TB: every On Watch arm was stale because those clubs had stopped
playing. This replay rebuilds that topology on a disposable PostgreSQL
publication: the seven clubs' last games (and their relievers' last outings) sit
outside the 14-day active window while every other club played yesterday, so the
completed-game ledger stays complete. The publication is made by the canonical
publisher and recertified by the read-only harness. Nothing about the expected
outcome is hard-coded per team: the assertions are the corrected contract.
"""

from datetime import timedelta

import pytest

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from services import publication_truth_certification as certification
from services.mlb_club_directory import MLB_CLUBS
from tests.test_trusted_publication_rehearsal import _TonightRehearsal, drop_test_schema
from utils.db import db


IDLE_CLUBS = ('WSH', 'COL', 'TEX', 'MIN', 'MIA', 'AZ', 'TB')
IDLE_DAYS = 20


@pytest.fixture(scope='module')
def replay():
    from api import bullpen as bullpen_api

    patch = pytest.MonkeyPatch()
    # install_public_serving_authority wraps this attribute process-wide; leave
    # it as found so later publications in the run are not wrapped twice.
    patch.setattr(bullpen_api, 'build_bullpen_dashboard_payload',
                  bullpen_api.build_bullpen_dashboard_payload)
    rehearsal = _TonightRehearsal(patch, name='evidence quality replay')
    context = rehearsal.app.app_context()
    context.push()
    try:
        rehearsal.setup()
        idle_team_ids = {
            club.team_id for club in MLB_CLUBS if club.abbreviation in IDLE_CLUBS
        }
        idle_day = rehearsal.reference_date - timedelta(days=IDLE_DAYS)
        pitcher_ids = [
            row.id for row in Pitcher.query.filter(Pitcher.team_id.in_(idle_team_ids)).all()
        ]
        game_pks = [
            row.mlb_game_pk for row in
            GameLog.query.filter(GameLog.pitcher_id.in_(pitcher_ids)).all()
        ]
        # The idle clubs' season ended IDLE_DAYS ago: move their last games and
        # outings there (outside the active window AND the ledger window).
        for model, column in (
            (GameLog, GameLog.mlb_game_pk),
            (ScheduledGame, ScheduledGame.game_pk),
            (PostgameProcessedGame, PostgameProcessedGame.mlb_game_pk),
        ):
            for row in model.query.filter(column.in_(game_pks)).all():
                row.game_date = idle_day
        db.session.commit()
        snapshot = rehearsal.publish('replay_4496')
        report = certification.certify_snapshot(snapshot)
        yield {
            'snapshot': snapshot, 'report': report,
            'idle_team_ids': idle_team_ids, 'idle_pitcher_ids': set(pitcher_ids),
        }
    finally:
        db.session.rollback()
        db.session.remove()
        drop_test_schema(rehearsal.app)
        context.pop()
        patch.undo()


def _idle(report, key, idle_team_ids):
    return {
        int(team_id): value for team_id, value in report[key].items()
        if int(team_id) in idle_team_ids
    }


def test_the_replay_topology_is_the_certified_one(replay):
    assert len(replay['idle_team_ids']) == 7
    assert replay['report']['subject']['appearance_ledger_complete_at_audit_time'] is True


def test_p1_1_no_stale_arm_is_on_watch_and_idle_arms_read_confirmed_rest(replay):
    report = replay['report']
    league = report['league_arm_attribution']
    assert league['monitor_stale'] == 0
    assert league['monitor_missing'] == 0
    assert not [f for f in report['findings']
                if f['issue'] == 'on_watch_from_stale_or_missing_evidence']
    for team_id, team in _idle(report, 'arm_attribution', replay['idle_team_ids']).items():
        counts = team['counts']
        assert counts['monitor_total'] == 0, team_id
        assert counts['stale_arms'] >= 1, team_id
        assert counts['available_from_confirmed_rest'] == counts['stale_arms'], team_id
        for arm in team['arms']:
            if arm['data_state'] == 'stale':
                assert arm['availability_status'] == 'Available'
                assert arm['operating_basis'] == 'ledger_confirmed_rest'
                assert arm['public_form'] == 'Available'
        board = team['board_on_watch_group']
        assert board is not None and board['count'] == 0


def test_p1_4_the_frozen_evidence_scope_names_the_idle_arms(replay):
    report = replay['report']
    for team_id, state in _idle(report, 'team_state', replay['idle_team_ids']).items():
        scope = state['evidence_scope']
        assert scope is not None, team_id
        assert scope['ledger_confirmed_rest_count'] >= 1
        assert 'complete game records confirm' in scope['note']
    for team_id, state in report['team_state'].items():
        if int(team_id) not in replay['idle_team_ids']:
            scope = state['evidence_scope']
            assert scope is not None and scope['ledger_confirmed_rest_count'] == 0


def test_the_hypothetical_no_longer_depends_on_evidence_quality(replay):
    """The audit-only hypothetical that proved P1-1 now finds nothing to change."""
    report = replay['report']
    assert not [f for f in report['findings']
                if f['issue'] == 'team_state_depends_on_evidence_quality_monitor']
    for state in report['team_state'].values():
        assert state['monitor_from_evidence_quality'] == 0
        assert state['hypothetical']['would_differ'] is False


def test_receipts_are_stamped_with_the_new_method(replay):
    report = replay['report']
    assert {state['receipt_method_version'] for state in report['team_state'].values()} == {
        'v3_phase_6'}


def test_the_separate_days_since_carry_forward_is_still_reported(replay):
    """Out of scope here and reported separately: an idle arm's frozen days-since
    comes from a stored score that stopped advancing. The harness keeps naming it."""
    report = replay['report']
    mismatches = [
        mismatch
        for team in _idle(report, 'workload', replay['idle_team_ids']).values()
        for mismatch in team['mismatches']
        if 'days_since_last_appearance' in mismatch['diff']
    ]
    assert mismatches
    assert all(m['stored_score_carry_forward_signature'] for m in mismatches)
    assert {m['pitcher_id'] for m in mismatches} <= replay['idle_pitcher_ids']
    for mismatch in mismatches:
        assert set(mismatch['diff']) == {'days_since_last_appearance'}


def test_18_to_21_every_surface_inherits_the_frozen_receipt(replay):
    """Tonight, Matchup, the Team Board (and through it Dashboard and share pages)
    read the one frozen receipt the corrected classifier produced at publication."""
    from services import current_bullpen_comparison
    from services import public_serving_authority as authority
    from services import tonight_read_model
    from services.team_board_snapshot_team_state import receipt_value

    snapshot = replay['snapshot']
    for club in MLB_CLUBS:
        present, receipt = receipt_value(snapshot, club.team_id)
        assert present is True
        tonight = tonight_read_model._team_state(snapshot, club.team_id)
        board = authority._published_team_state(snapshot, club.team_id)
        matchup, _identity = current_bullpen_comparison._team_state(snapshot, club.team_id)
        assert tonight['public_state'] == receipt['public_state'], club.abbreviation
        assert board['public_state'] == receipt['public_state'], club.abbreviation
        assert (matchup or {}).get('public_state') == (
            receipt['public_state'] if receipt.get('available') else None), club.abbreviation
