"""WP-0.1: stop false current bullpen reads (EOS-001, EOS-002, EOS-004).

Fixtures are modelled on the real 2026 end-of-season record committed to this
repository by the production distribution job:

* Washington (MLB id 120) last played 2026-09-27 and did not reach the
  postseason. Its frozen share artifact
  ``frontend/public/share/178c7a7f812645e6b6d5126e06a92aab`` (data through
  2026-10-27, snapshot 5656) published "Vulnerable ... fewer clean options
  available after recent work" with nineteen relievers On Watch.
* The 2026 League Championship Series: Milwaukee (158) swept Los Angeles (119)
  4-0; Tampa Bay (139) beat Cleveland (114) 4-2. The World Series is
  Milwaukee vs Tampa Bay.

Series game dates below are illustrative; the series structure and outcomes
are the real ones.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from api.team_operations import _readiness_record
from services.availability import (
    ACTIVE_WINDOW_DAYS,
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    classify_availability,
)
from services.club_competition_status import (
    BASIS_AWAITING_NEXT_ROUND,
    BASIS_ELIMINATED,
    BASIS_LOOKUP_FAILED,
    BASIS_NO_SCHEDULE_EVIDENCE,
    BASIS_NOT_IN_POSTSEASON,
    BASIS_POSTSEASON_COMPLETE,
    BASIS_REGULAR_SEASON_IN_PROGRESS,
    BASIS_UNRESOLVED,
    BASIS_UPCOMING_GAME,
    STATUS_ACTIVE,
    STATUS_SEASON_COMPLETE,
    STATUS_UNDETERMINED,
    classify_club_competition_status,
    lookup_failed_status,
)
from services.pitcher_public_labels import build_public_arm_read
from services.team_state_eligibility import (
    BLOCK_NOT_IN_ACTIVE_COMPETITION,
    evaluate_team_state_eligibility,
    is_withheld_for_competition,
)
from services.team_state_plausibility import (
    CHECK_ARM_TEAM_MISMATCH,
    CHECK_DATE_CONTRADICTION,
    CHECK_INACTIVE_CLUB_CURRENT,
    CHECK_INACTIVITY_CONSTRAINT,
    CHECK_LOOKUP_FAILED,
    CHECK_MAJORITY_VULNERABLE,
    CHECK_VULNERABLE_SHIFT,
    TeamStatePlausibilityBlocked,
    evaluate_publication_plausibility,
    require_publication_plausibility,
)
from services.team_state_public_vocabulary import (
    TEAM_STATE_COMPETITION_UNCONFIRMED,
    TEAM_STATE_SEASON_COMPLETE,
    is_competition_withholding,
    public_team_state,
)
from services.team_state_source import TeamStateSnapshotAuthority, TeamStateSource
from team_operations import assemble_bullpen_readiness


WSH, LAD, MIL, TB, CLE, NYY = 120, 119, 158, 139, 114, 147
REGULAR_SEASON_END = date(2026, 9, 27)
DATA_THROUGH = date(2026, 10, 27)
REFERENCE = date(2026, 10, 28)


# ---------------------------------------------------------------------------
# Arm-level fixtures
# ---------------------------------------------------------------------------


class Score:
    def __init__(self, raw_score=12.0, risk_level='LOW'):
        self.raw_score = raw_score
        self.risk_level = risk_level


class Log:
    def __init__(self, game_date, pitches, outs=3):
        self.game_date = game_date
        self.pitches_thrown = pitches
        self.innings_pitched_outs = outs
        self.innings_pitched = outs / 3
        self.games_started = 0


def _arm(latest, logs=(), score=None, reference=REFERENCE):
    return classify_availability(
        score=score or Score(),
        game_logs=list(logs),
        reference_date=reference,
        latest_game_date=latest,
    )


# 1. An arm that has not pitched for 14+ days.
@pytest.mark.parametrize('idle_days', [ACTIVE_WINDOW_DAYS + 1, 31, 150])
def test_idle_arm_is_rested_not_constrained(idle_days):
    result = _arm(REFERENCE - timedelta(days=idle_days))

    assert result['availability_status'] == STATUS_AVAILABLE
    assert result['data_state'] == 'stale'
    assert result['reasons'] == [f'No appearances in the last {ACTIVE_WINDOW_DAYS} days']
    # A workload fact only: never a claim about physical or medical readiness.
    assert any('not physical or medical readiness' in note for note in result['limitations'])
    assert build_public_arm_read(availability=result)['label'] == 'Clean Option'


def test_more_rest_never_moves_an_arm_out_of_the_clean_count():
    statuses = [
        _arm(REFERENCE - timedelta(days=days))['availability_status']
        for days in range(5, 60)
    ]
    assert set(statuses) == {STATUS_AVAILABLE}


# 2. A reliever returning after an extended break.
def test_returning_reliever_is_read_from_his_actual_workload():
    yesterday = REFERENCE - timedelta(days=1)
    result = _arm(yesterday, logs=[Log(yesterday, 27)])

    assert result['data_state'] == 'fresh'
    assert result['availability_status'] == 'Limited'
    assert '27 pitches yesterday' in result['reasons']
    # The month he did not pitch adds nothing to the read.
    assert not any('No appearances' in reason for reason in result['reasons'])


# 3. A heavily used reliever stays genuinely constrained.
def test_heavily_used_reliever_keeps_his_restriction():
    days = [REFERENCE - timedelta(days=offset) for offset in (1, 2, 3)]
    avoid = _arm(days[0], logs=[Log(day, 30) for day in days])
    assert avoid['availability_status'] == STATUS_AVOID
    assert build_public_arm_read(availability=avoid)['label'] == 'Limited Rest'

    yesterday = REFERENCE - timedelta(days=1)
    unavailable = _arm(yesterday, logs=[Log(yesterday, 52, outs=9)])
    assert unavailable['availability_status'] == STATUS_UNAVAILABLE
    assert build_public_arm_read(availability=unavailable)['label'] == 'Unavailable'


# 4. An arm lacking sufficient evidence.
def test_missing_evidence_is_a_limited_read_and_never_a_constraint():
    result = classify_availability(score=None, game_logs=[], reference_date=REFERENCE)

    assert result['data_state'] == 'missing'
    assert build_public_arm_read(availability=result)['label'] == 'Limited Read'
    record = _readiness_record({
        'availability': result,
        'pitcher': SimpleNamespace(throws='R', active=True),
    })
    # Unknown evidence lands in the unknown bucket, not the moderate one.
    assert record['has_availability'] is False


# 5. A pitcher on an inactive roster.
def test_inactive_roster_arm_is_never_a_clean_option():
    rested = _arm(REFERENCE - timedelta(days=40))
    read = build_public_arm_read(
        availability=rested,
        roster_status={'status': 'IL_60', 'is_active_mlb': False, 'is_inactive_context': True},
    )
    assert read['label'] == 'Unavailable'

    readiness = _assemble([_readiness_record({
        'availability': rested,
        'pitcher': SimpleNamespace(throws='R', active=False),
    })] + _clean_records(6))
    evidence = readiness['team_state_evidence']
    assert evidence['active_pitcher_count'] == 6
    assert evidence['clean_count'] == 6


# ---------------------------------------------------------------------------
# Team State: the Washington October 2026 case
# ---------------------------------------------------------------------------

TRUST = {
    'confidence': 'high',
    'confidence_reasons': ['complete_active_bullpen_coverage'],
    'data_state': 'fresh',
    'source_evidence_state': 'represented',
    'governance_state': 'internal_uncertified',
    'generated_at': '2026-10-28T10:00:00+00:00',
    'limitations': [],
    'explanations': [],
    'refusal_reasons': [],
    'trust_validation_errors': [],
    'ranking_applied': False,
    'selection_made': False,
}
FRESHNESS = {
    'freshness_state': 'current',
    'data_through': DATA_THROUGH.isoformat(),
    'latest_workload_date': DATA_THROUGH.isoformat(),
    'last_successful_sync': '2026-10-28T10:00:00+00:00',
    'latest_sync_status': 'success',
    'latest_fatigue_calculated_at': '2026-10-28T10:00:00+00:00',
    'generated_at': '2026-10-28T10:00:00+00:00',
    'stale_warning': None,
    'missing_data_warning': None,
    'limitations': [],
}


def _assemble(records, team_id=WSH):
    return assemble_bullpen_readiness(
        team={'team_id': team_id, 'team_name': 'Washington Nationals', 'team_abbreviation': 'WSH'},
        pitcher_records=tuple(records),
        trust_metadata=TRUST,
        freshness=FRESHNESS,
        generated_at='2026-10-28T10:00:00+00:00',
    )


def _clean_records(count):
    return [
        _readiness_record({
            'availability': _arm(REFERENCE - timedelta(days=2), logs=[
                Log(REFERENCE - timedelta(days=2), 8),
            ]),
            'latest_game_date': REFERENCE - timedelta(days=2),
            'pitcher': SimpleNamespace(throws='R', active=True),
        })
        for _ in range(count)
    ]


def _washington_records():
    """Nineteen active relievers whose last appearances fall on or before
    2026-09-27, read against 2026-10-28 (the snapshot-5656 reference date)."""
    records = []
    for index in range(19):
        latest = REGULAR_SEASON_END - timedelta(days=index % 6)
        records.append(_readiness_record({
            'availability': _arm(latest),
            'latest_game_date': latest,
            'pitcher': SimpleNamespace(throws='R' if index % 3 else 'L', active=True),
        }))
    return records


# 10. A bullpen that previously suffered an erroneous Vulnerable classification.
def test_washington_october_bullpen_is_no_longer_vulnerable_from_inactivity():
    readiness = _assemble(_washington_records())
    evidence = readiness['team_state_evidence']

    # Before WP-0.1 every one of these arms was Monitor, so clean_count was 0
    # and the margin floor published Vulnerable.
    assert evidence['clean_count'] == 19
    assert evidence['moderate_count'] == 0
    assert evidence['severe_count'] == 0
    assert readiness['readiness']['status_code'] == 'operationally_stable'
    assert not any(
        constraint['constraint_id'] == 'coverage_partial'
        for constraint in readiness['constraints']
    )


def test_washington_october_read_is_withheld_as_season_complete():
    readiness = _assemble(_washington_records())
    status = classify_club_competition_status(
        WSH, REFERENCE, schedule_rows=_postseason_schedule(), winner_by_game=_decisions(),
    )
    readiness['season_context'] = status.to_dict()

    block = public_team_state(readiness)
    assert status.status == STATUS_SEASON_COMPLETE
    assert block['available'] is False
    assert block['public_label'] is None
    assert block['outcome'] == TEAM_STATE_SEASON_COMPLETE
    assert block['data_through'] == DATA_THROUGH.isoformat()
    assert 'historical context, not a current pregame read' in block['unavailable_message']
    # The computed state stays inspectable as dated evidence.
    assert readiness['readiness']['status_code'] == 'operationally_stable'


# ---------------------------------------------------------------------------
# Club competition status
# ---------------------------------------------------------------------------

_PK = iter(range(900000, 999999))


def _row(team, opponent, game_date, game_type='R', state='final', games_in_series=None,
         code=None, game_pk=None):
    return SimpleNamespace(
        team_id=team, opponent_team_id=opponent, game_pk=game_pk or next(_PK),
        game_date=game_date, game_type=game_type, status_state=state,
        status_code=code, games_in_series=games_in_series,
    )


def _series(home, away, game_type, length, results, start):
    """Rows for both clubs; ``results`` lists the winning club per final game."""
    rows, winners = [], {}
    for index in range(length):
        game_pk = next(_PK)
        game_date = start + timedelta(days=index)
        if index < len(results):
            state, code = 'final', 'F'
            winners[game_pk] = results[index]
        else:
            state, code = 'scheduled', 'S'
        for team, opponent in ((home, away), (away, home)):
            rows.append(_row(team, opponent, game_date, game_type, state,
                             games_in_series=length, code=code, game_pk=game_pk))
    return rows, winners


_SCHEDULE = None


def _postseason_schedule_and_decisions():
    global _SCHEDULE
    if _SCHEDULE is None:
        rows = [
            _row(team, None, REGULAR_SEASON_END)
            for team in (WSH, LAD, MIL, TB, CLE, NYY)
        ]
        winners = {}
        nlcs, w1 = _series(MIL, LAD, 'L', 7, [MIL, MIL, MIL, MIL], date(2026, 10, 12))
        alcs, w2 = _series(TB, CLE, 'L', 7, [TB, CLE, TB, CLE, TB, TB], date(2026, 10, 13))
        world, w3 = _series(MIL, TB, 'W', 7, [MIL, TB, MIL, MIL], date(2026, 10, 23))
        rows += nlcs + alcs + world
        for item in (w1, w2, w3):
            winners.update(item)
        _SCHEDULE = (rows, winners)
    return _SCHEDULE


def _postseason_schedule():
    return _postseason_schedule_and_decisions()[0]


def _decisions():
    return _postseason_schedule_and_decisions()[1]


def _status(team, reference=REFERENCE, rows=None, winners=None):
    return classify_club_competition_status(
        team, reference,
        schedule_rows=_postseason_schedule() if rows is None else rows,
        winner_by_game=_decisions() if winners is None else winners,
    )


# 6. An eliminated regular-season team.
def test_club_that_missed_the_postseason_is_season_complete():
    status = _status(WSH)
    assert status.status == STATUS_SEASON_COMPLETE
    assert status.basis == BASIS_NOT_IN_POSTSEASON
    assert status.last_final_game_date == REGULAR_SEASON_END


def test_world_series_clubs_with_pending_games_are_active():
    for team in (MIL, TB):
        status = _status(team)
        assert status.status == STATUS_ACTIVE
        assert status.basis == BASIS_UPCOMING_GAME
        assert status.next_scheduled_game_date == date(2026, 10, 28)


def test_series_loser_is_season_complete_even_before_unneeded_games_retire():
    # LAD's remaining NLCS "if necessary" rows are still stored as scheduled.
    status = _status(LAD, reference=date(2026, 10, 16))
    assert status.status == STATUS_SEASON_COMPLETE
    assert status.basis == BASIS_ELIMINATED

    cle = _status(CLE, reference=date(2026, 10, 20))
    assert cle.status == STATUS_SEASON_COMPLETE
    assert cle.basis == BASIS_ELIMINATED


# 7. An active postseason team with a long scheduling gap.
def test_pennant_winner_waiting_days_for_the_next_round_stays_active():
    rows = [row for row in _postseason_schedule() if row.game_type != 'W']
    status = _status(MIL, reference=date(2026, 10, 19), rows=rows)
    assert status.status == STATUS_ACTIVE
    assert status.basis == BASIS_AWAITING_NEXT_ROUND
    assert status.next_scheduled_game_date is None


def test_regular_season_off_days_do_not_end_a_season():
    rows = [_row(NYY, 111, date(2026, 7, 12))]
    status = _status(NYY, reference=date(2026, 7, 16), rows=rows, winners={})
    assert status.status == STATUS_ACTIVE
    assert status.basis == BASIS_REGULAR_SEASON_IN_PROGRESS


# 8. A team whose final game has completed.
def test_world_series_decided_completes_every_season():
    rows, winners = _postseason_schedule_and_decisions()
    winners = dict(winners)
    final_world_series = [
        row for row in rows
        if row.game_type == 'W' and row.status_state != 'final'
    ]
    closing = final_world_series[0]
    for row in rows:
        if row.game_pk == closing.game_pk:
            row_state = 'final'
            row.status_state, row.status_code = row_state, 'F'
    winners[closing.game_pk] = MIL
    try:
        for team in (MIL, TB, WSH, LAD):
            status = _status(team, reference=date(2026, 10, 29), rows=rows, winners=winners)
            assert status.status == STATUS_SEASON_COMPLETE
            assert status.basis == BASIS_POSTSEASON_COMPLETE
    finally:
        for row in rows:
            if row.game_pk == closing.game_pk:
                row.status_state, row.status_code = 'scheduled', 'S'


# 9. A season transition with uncertain status.
def test_unconfirmed_status_never_becomes_a_definitive_claim():
    rows = [row for row in _postseason_schedule() if row.game_type != 'W']
    # The decisions for the NLCS are missing, so neither side has clinched.
    status = _status(LAD, reference=date(2026, 10, 19), rows=rows, winners={})
    assert status.status == STATUS_UNDETERMINED
    assert status.basis == BASIS_UNRESOLVED

    block = public_team_state({
        'readiness': {'status_code': 'operationally_stable'},
        'freshness': {'data_through': '2026-10-18'},
        'season_context': status.to_dict(),
    })
    assert block['available'] is False
    assert block['outcome'] == TEAM_STATE_COMPETITION_UNCONFIRMED

    assert _status(LAD, rows=[], winners={}).basis == BASIS_NO_SCHEDULE_EVIDENCE
    # Spring training and exhibition games are not competition.
    spring = [_row(LAD, 158, date(2027, 3, 1), game_type='S', state='scheduled')]
    assert _status(LAD, reference=date(2027, 2, 27), rows=spring, winners={}).status == (
        STATUS_UNDETERMINED
    )


def test_eligibility_refuses_a_current_artifact_for_a_withheld_club():
    readiness = _assemble(_washington_records())
    readiness['readiness']['summary'] = 'Current bullpen state.'
    readiness['season_context'] = _status(WSH).to_dict()
    source = TeamStateSource(
        team_id=WSH, team_valid=True,
        snapshot=TeamStateSnapshotAuthority(
            snapshot_id=5656, sync_run_id=95956, data_through=DATA_THROUGH,
            published_at=None, unavailable_reason=None,
        ),
        readiness=readiness,
    )
    result = evaluate_team_state_eligibility(source)
    assert result.eligible is False
    assert BLOCK_NOT_IN_ACTIVE_COMPETITION in result.blocking_conditions
    assert is_withheld_for_competition(result)

    readiness['season_context'] = _status(MIL).to_dict()
    assert evaluate_team_state_eligibility(source).eligible is True


# ---------------------------------------------------------------------------
# 11. Historical snapshots and immutable share behavior
# ---------------------------------------------------------------------------


def _receipt_snapshot(snapshot_id, data_through, receipts):
    return SimpleNamespace(
        id=snapshot_id, data_through=data_through,
        payload={'trusted_team_boards': {
            'contract': 'trusted_team_board_publication_v1',
            'data_through': data_through.isoformat(),
            'by_team_id': {str(team_id): {} for team_id in receipts},
            'frozen_team_state_by_team_id': receipts,
        }},
    )


def test_season_withholding_is_frozen_and_served_unchanged():
    from services.team_board_snapshot_team_state import make_receipt, receipt_value
    from services.team_state_vnext_production_proof import EXPECTED_METHOD_VERSION

    readiness = _assemble(_washington_records())
    readiness['season_context'] = _status(WSH).to_dict()
    snapshot = SimpleNamespace(id=5656, data_through=DATA_THROUGH, payload={})
    receipt = make_receipt(snapshot, WSH, readiness, method_version=EXPECTED_METHOD_VERSION)

    assert receipt['value']['outcome'] == TEAM_STATE_SEASON_COMPLETE
    assert receipt['season_context']['basis'] == BASIS_NOT_IN_POSTSEASON
    served = _receipt_snapshot(5656, DATA_THROUGH, {str(WSH): receipt})
    present, value = receipt_value(served, WSH)
    assert present is True
    assert value == receipt['value']
    assert is_competition_withholding(value)


def test_any_other_unavailable_value_still_cannot_be_frozen():
    from services.team_board_snapshot_team_state import make_receipt

    readiness = _assemble(_washington_records())
    readiness['readiness']['status_code'] = 'data_limited'
    snapshot = SimpleNamespace(id=5656, data_through=DATA_THROUGH, payload={})
    with pytest.raises(ValueError, match='snapshot_team_state_public_value_unavailable'):
        make_receipt(snapshot, WSH, readiness, method_version='v3_phase_5')


def test_team_state_comparison_refuses_the_availability_method_boundary(monkeypatch):
    from services import team_board_snapshot_team_state as receipts_module
    from services import what_changed_comparison_identity

    monkeypatch.setattr(
        what_changed_comparison_identity, 'validate_snapshot_pair',
        lambda *_args, **_kwargs: None,
    )

    def receipt(snapshot_id, data_through, state, method):
        item = {
            'contract': receipts_module.CONTRACT, 'team_id': TB,
            'dashboard_snapshot_id': snapshot_id,
            'represented_date': data_through.isoformat(),
            'method_version': 'v3_phase_5',
            'value': {
                'contract': 'team_state_public_v1', 'available': True,
                'public_state': state, 'public_label': state.title(),
                'data_through': data_through.isoformat(),
            },
        }
        if method is not None:
            item['availability_method_version'] = method
        return item

    previous_date = date(2026, 10, 26)
    previous = _receipt_snapshot(
        5625, previous_date, {str(TB): receipt(5625, previous_date, 'vulnerable', None)},
    )
    current = _receipt_snapshot(
        5656, DATA_THROUGH,
        {str(TB): receipt(5656, DATA_THROUGH, 'fresh', 'availability_rest_by_absence_v2')},
    )
    # Vulnerable -> Fresh across the semantics change is a method change, not
    # a baseball change, so no Team State change event is reported.
    result = receipts_module.compare_exact_team_state(previous, current, TB, {})
    assert result['status'] == 'unavailable'
    assert result['reason_code'] == 'availability_method_boundary'
    assert result['event'] is None

    same = _receipt_snapshot(
        5625, previous_date,
        {str(TB): receipt(5625, previous_date, 'vulnerable', 'availability_rest_by_absence_v2')},
    )
    changed = receipts_module.compare_exact_team_state(same, current, TB, {})
    assert changed['status'] == 'changed'
    assert changed['event']['current_state'] == 'fresh'


def test_league_listing_shows_the_frozen_season_withholding():
    from services.league_team_state_listing import _row_state
    from services.team_board_snapshot_team_state import make_receipt

    readiness = _assemble(_washington_records())
    readiness['season_context'] = _status(WSH).to_dict()
    snapshot = SimpleNamespace(id=5656, data_through=DATA_THROUGH, sync_run_id=95956, payload={})
    receipt = make_receipt(snapshot, WSH, readiness, method_version='v3_phase_5')
    served = _receipt_snapshot(5656, DATA_THROUGH, {str(WSH): receipt})
    served.sync_run_id = 95956

    state = _row_state(None, served, WSH)
    assert state['outcome'] == TEAM_STATE_SEASON_COMPLETE
    assert state['available'] is False


def test_static_preview_carries_no_current_baseball_point_for_a_withheld_club():
    from services.team_story_previews import build_team_story_preview

    readiness = _assemble(_washington_records())
    readiness['season_context'] = _status(WSH).to_dict()
    board = {
        'team': {'team_id': WSH, 'team_name': 'Washington Nationals', 'team_abbreviation': 'WSH'},
        'team_state': public_team_state(readiness),
        'context': {'health': {'reasons': ['Nineteen relievers are in the On Watch group.']}},
        'publication_authority': {
            'snapshot_id': 5656, 'sync_run_id': 95956,
            'data_through': DATA_THROUGH.isoformat(),
            'contract': 'trusted_dashboard_publication_v1',
        },
        'freshness': {'data_through': DATA_THROUGH.isoformat()},
    }
    preview = build_team_story_preview(
        team=board['team'], board=board, story=None, expected_snapshot_id=5656,
    )
    assert preview['representation'] == 'dated_team_read'
    assert preview['team_state_label'] is None
    assert preview['baseball_point'] is None
    assert 'On Watch' not in preview['og_description']
    assert "This club's season is complete" in preview['og_description']
    assert preview['og_title'] == 'Washington Nationals Bullpen Read'


# ---------------------------------------------------------------------------
# 12. Publication plausibility failures
# ---------------------------------------------------------------------------


def _entry(team_id, public_state, *, status='active', basis='upcoming_scheduled_game',
           clean=6, arm_reads=None, last_final=DATA_THROUGH, reference=REFERENCE):
    return {
        'team_id': team_id,
        'public_state': public_state,
        'season_context': {
            'status': status, 'basis': basis,
            'reference_date': reference.isoformat(),
            'last_final_game_date': last_final.isoformat() if last_final else None,
        },
        'availability_reference_date': reference,
        'partition': {'clean_count': clean},
        'arm_reads': arm_reads or [],
    }


def _arm_read(pitcher_id, key, data_state='fresh'):
    return {
        'pitcher_id': pitcher_id,
        'public_read': {'key': key},
        'evidence_state': {'data_state': data_state},
    }


def test_october_2026_postseason_publication_passes_cleanly():
    teams = [_entry(MIL, 'vulnerable'), _entry(TB, 'vulnerable')] + [
        _entry(100 + index, None, status='season_complete', basis=BASIS_NOT_IN_POSTSEASON,
               last_final=REGULAR_SEASON_END)
        for index in range(28)
    ]
    result = evaluate_publication_plausibility(teams, data_through=DATA_THROUGH)
    # Two published clubs cannot trip a distribution check: no false alarm.
    assert result['blocked'] is False
    assert result['warning_checks'] == []
    assert result['published_team_count'] == 2
    require_publication_plausibility(result)


def test_inactive_club_published_as_current_blocks_publication():
    teams = [_entry(WSH, 'vulnerable', status='season_complete', basis=BASIS_NOT_IN_POSTSEASON)]
    result = evaluate_publication_plausibility(teams, data_through=DATA_THROUGH)
    assert result['blocking_checks'] == [CHECK_INACTIVE_CLUB_CURRENT]
    with pytest.raises(TeamStatePlausibilityBlocked) as raised:
        require_publication_plausibility(result)
    assert raised.value.publication_evidence['findings'][0]['team_ids'] == [WSH]


def test_inactivity_counted_as_constraint_blocks_publication():
    arms = [_arm_read(1, 'watch_arm', 'stale'), _arm_read(2, 'clean_option')]
    result = evaluate_publication_plausibility(
        [_entry(NYY, 'stretched', clean=1, arm_reads=arms)], data_through=DATA_THROUGH,
    )
    assert CHECK_INACTIVITY_CONSTRAINT in result['blocking_checks']


def test_unreadable_competition_authority_blocks_publication():
    status = lookup_failed_status(NYY, REFERENCE)
    assert status.basis == BASIS_LOOKUP_FAILED
    teams = [_entry(NYY, None, status=status.status, basis=status.basis)]
    result = evaluate_publication_plausibility(teams, data_through=DATA_THROUGH)
    assert result['blocking_checks'] == [CHECK_LOOKUP_FAILED]


def test_dates_that_contradict_the_publication_block_it():
    # A final game after data-through is ordinarily ingestion lag: surfaced,
    # not blocking, so the previous-day read is not withheld for it.
    teams = [_entry(MIL, 'fresh', last_final=DATA_THROUGH + timedelta(days=1))]
    result = evaluate_publication_plausibility(teams, data_through=DATA_THROUGH)
    assert result['blocked'] is False
    assert result['warning_checks'] == ['final_game_after_data_through']

    teams = [_entry(MIL, 'fresh')]
    teams[0]['season_context']['reference_date'] = '2026-10-20'
    result = evaluate_publication_plausibility(teams, data_through=DATA_THROUGH)
    assert result['blocking_checks'] == [CHECK_DATE_CONTRADICTION]


def test_league_wide_collapse_is_surfaced_without_blocking():
    states = ['vulnerable'] * 19 + ['stretched'] * 8 + ['fresh'] * 3
    teams = [_entry(200 + index, state) for index, state in enumerate(states)]
    previous = {200 + index: 'fresh' for index in range(30)}
    result = evaluate_publication_plausibility(
        teams, data_through=DATA_THROUGH, previous_states=previous,
    )
    assert result['blocked'] is False
    assert CHECK_MAJORITY_VULNERABLE in result['warning_checks']
    assert CHECK_VULNERABLE_SHIFT in result['warning_checks']


def test_arm_reads_disagreeing_with_the_partition_are_surfaced():
    arms = [_arm_read(index, 'clean_option') for index in range(4)]
    result = evaluate_publication_plausibility(
        [_entry(NYY, 'fresh', clean=6, arm_reads=arms)], data_through=DATA_THROUGH,
    )
    assert result['blocked'] is False
    assert CHECK_ARM_TEAM_MISMATCH in result['warning_checks']


def test_monitor_status_is_unchanged_for_real_recent_workload():
    yesterday = REFERENCE - timedelta(days=1)
    result = _arm(yesterday, logs=[Log(yesterday, 16)])
    assert result['availability_status'] == STATUS_MONITOR


def test_withheld_club_without_a_partition_counts_as_a_governed_withholding():
    from services.team_state_vnext_production_proof import (
        _candidate_team_entry,
        _governed_withholding,
    )

    snapshot = SimpleNamespace(
        id=5656, sync_run_id=95956, data_through=DATA_THROUGH,
        availability_reference_date=REFERENCE,
    )
    readiness = {
        'contract_version': 'v3_phase_5',
        'readiness': {'status_code': 'refused'},
        'freshness': {},
        'season_context': _status(WSH).to_dict(),
    }
    entry = _candidate_team_entry(
        snapshot, WSH, readiness,
        {'membership_reference_date': DATA_THROUGH, 'availability_reference_date': REFERENCE},
    )
    assert entry['final_team_state']['published_public_state'] is None
    assert entry['final_team_state']['withholding_outcome'] == TEAM_STATE_SEASON_COMPLETE
    assert entry['contract_a_reproduction']['reproduced'] is None
    assert _governed_withholding(entry) is True


def test_withheld_club_receipt_binds_to_the_publication_date():
    from services.team_board_snapshot_team_state import make_receipt

    readiness = {
        'readiness': {'status_code': 'refused'},
        'season_context': _status(WSH).to_dict(),
    }
    snapshot = SimpleNamespace(id=5656, data_through=DATA_THROUGH, payload={})
    receipt = make_receipt(snapshot, WSH, readiness, method_version='v3_phase_5')
    assert receipt['value']['outcome'] == TEAM_STATE_SEASON_COMPLETE
    assert receipt['value']['data_through'] == DATA_THROUGH.isoformat()


def test_since_yesterday_withholds_rested_counts_across_the_method_boundary():
    from tests.test_what_changed_since_yesterday import (
        dashboard_payload,
        snapshot,
        trusted_comparison,
    )
    from services.availability import AVAILABILITY_METHOD_VERSION
    from services.what_changed_since_yesterday import REASON_AVAILABILITY_METHOD_BOUNDARY

    current = dashboard_payload([snapshot(clean=13)], data_through='2026-06-19')
    current['availability_method_version'] = AVAILABILITY_METHOD_VERSION
    prior = dashboard_payload([snapshot(clean=0)], data_through='2026-06-18')

    # Thirteen "new" rested options here would be the method change, not
    # baseball, so the comparison is withheld rather than reported.
    result = trusted_comparison(current, prior)
    assert result['change_count'] == 0
    assert REASON_AVAILABILITY_METHOD_BOUNDARY in result['reason_codes']
    assert any('different availability methods' in note for note in result['limitations'])

    prior['availability_method_version'] = AVAILABILITY_METHOD_VERSION
    compared = trusted_comparison(current, prior)
    assert REASON_AVAILABILITY_METHOD_BOUNDARY not in compared['reason_codes']
