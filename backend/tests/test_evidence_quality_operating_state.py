"""Evidence quality is not operating state (availability engine v2, Team State v3_phase_6).

Regression contract for the truth-certification remediation
(docs/decisions/2026-10-07-evidence-quality-operating-state-separation.md):

* evidence quality alone never creates workload concern (no stale/missing arm is
  On Watch or moderate);
* uncertainty is never turned into a clean read or a Fresh team;
* Team State never worsens because evidence ages while no new workload occurs,
  and still responds to real new workload and to real recovery.

Pure Python except where a test says otherwise: the classifier and the Team State
aggregation are exercised directly, end to end, from game-log-shaped inputs.
"""

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.team_operations import _readiness_record
from services import availability as engine
from services import bullpen_board
from services.availability import (
    ACTIVE_WINDOW_DAYS,
    AVAILABILITY_METHOD_VERSION,
    OPERATING_BASIS_LEDGER_CONFIRMED_REST,
    OPERATING_BASIS_PARTIAL_WORKLOAD,
    OPERATING_BASIS_WORKLOAD,
    STATUS_AVAILABLE,
    STATUS_LIMITED,
    STATUS_MONITOR,
    classify_availability,
)
from services.availability_snapshot import _apply_workload_fetch_failure
from services.fatigue import calculate_fatigue
from services.team_evidence_scope import author_evidence_scope, valid_evidence_scope
from team_operations import TEAM_STATE_METHOD_VERSION, assemble_bullpen_readiness


REPO_ROOT = Path(__file__).resolve().parents[2]
REF = date(2026, 10, 7)

TRUST_HIGH = {
    'confidence': 'high',
    'confidence_reasons': ['complete_active_bullpen_coverage'],
    'data_state': 'fresh',
    'source_evidence_state': 'represented',
    'governance_state': 'internal_uncertified',
    'generated_at': '2026-10-07T00:00:00+00:00',
    'limitations': [],
    'explanations': [],
    'refusal_reasons': [],
    'trust_validation_errors': [],
    'ranking_applied': False,
    'selection_made': False,
}
FRESHNESS_CURRENT = {
    'freshness_state': 'current',
    'data_through': '2026-10-06',
    'latest_workload_date': '2026-10-06',
    'last_successful_sync': '2026-10-07T00:00:00+00:00',
    'latest_sync_status': 'success',
    'latest_fatigue_calculated_at': '2026-10-07T00:00:00+00:00',
    'generated_at': '2026-10-07T00:00:00+00:00',
    'stale_warning': None,
    'missing_data_warning': None,
    'limitations': [],
}
TEAM = {'team_id': 120, 'team_name': 'Fixture Nationals', 'team_abbreviation': 'WSH'}
RANK = {'operationally_stressed': 0, 'operationally_constrained': 1, 'operationally_stable': 2}


def _log(day, pitches=15, outs=3, started=0, game_type='R'):
    return SimpleNamespace(
        game_date=day, pitches_thrown=pitches, innings_pitched_outs=outs,
        innings_pitched=outs / 3, games_started=started, game_type=game_type,
        mlb_game_pk=hash((day, pitches, outs)) % 10_000_000,
    )


def _score(raw):
    return SimpleNamespace(raw_score=raw, risk_level='LOW')


def _classify(logs, *, ref=REF, score=None, rest_confirmed=False):
    logs = sorted(logs, key=lambda log: log.game_date, reverse=True)
    latest = logs[0].game_date if logs else None
    window = [log for log in logs if ref - timedelta(days=4) <= log.game_date <= ref]
    return classify_availability(
        score=score if score is not None else (_score(10.0) if logs else None),
        game_logs=window, reference_date=ref, latest_game_date=latest,
        rest_confirmed=rest_confirmed,
    )


def _record(availability, pitcher_id=1):
    return {
        'pitcher': SimpleNamespace(id=pitcher_id, throws='R', active=True),
        'availability': availability,
        'score': None,
        'latest_game_date': None,
    }


def _team(availabilities, trust=TRUST_HIGH):
    payload = assemble_bullpen_readiness(
        team=TEAM,
        pitcher_records=tuple(
            _readiness_record(_record(availability, index))
            for index, availability in enumerate(availabilities, start=1)
        ),
        trust_metadata=trust,
        freshness=FRESHNESS_CURRENT,
    )
    return payload['readiness']['status_code'], payload['team_state_evidence']


# ── Arm contract (availability engine v2) ────────────────────────────────────

def test_1_fresh_workload_monitor_remains_on_watch():
    availability = _classify([_log(REF - timedelta(days=1), pitches=16)])
    assert availability['availability_status'] == STATUS_MONITOR
    assert availability['operating_basis'] == OPERATING_BASIS_WORKLOAD
    assert availability['data_state'] == 'fresh'


def test_2_fresh_clean_arm_remains_clean():
    availability = _classify([_log(REF - timedelta(days=6), pitches=12)])
    assert availability['availability_status'] == STATUS_AVAILABLE
    assert availability['operating_basis'] == OPERATING_BASIS_WORKLOAD
    assert availability['confidence'] == 'high'


def test_3_stale_arm_with_complete_ledger_is_observed_rest_not_on_watch():
    logs = [_log(REF - timedelta(days=ACTIVE_WINDOW_DAYS + 3), pitches=30)]
    availability = _classify(logs, score=_score(88.0), rest_confirmed=True)
    assert availability['availability_status'] == STATUS_AVAILABLE
    assert availability['operating_basis'] == OPERATING_BASIS_LEDGER_CONFIRMED_REST
    assert availability['data_state'] == 'stale'
    assert availability['confidence'] == 'medium'


def test_4_missing_arm_is_evidence_uncertainty_not_workload():
    availability = _classify([])
    assert availability['availability_status'] is None
    assert availability['operating_basis'] is None
    assert availability['data_state'] == 'missing'
    assert availability['confidence'] == 'low'


def test_5_incomplete_ledger_fails_closed_for_a_stale_arm():
    logs = [_log(REF - timedelta(days=ACTIVE_WINDOW_DAYS + 3))]
    availability = _classify(logs, rest_confirmed=False)
    assert availability['availability_status'] is None
    assert availability['operating_basis'] is None
    assert availability['confidence'] == 'low'


def test_5b_rest_proof_fails_closed_on_error(monkeypatch):
    import services.appearance_ledger as ledger
    from services.availability_snapshot import rest_confirmed_for

    def boom(**_kwargs):
        raise RuntimeError('ledger unreadable')

    monkeypatch.setattr(ledger, 'build_appearance_ledger', boom)
    assert rest_confirmed_for(REF) is False
    assert rest_confirmed_for(None) is False


@pytest.mark.parametrize('rest_confirmed', [True, False])
def test_6_open_fetch_failure_fails_closed(rest_confirmed):
    stale = _classify(
        [_log(REF - timedelta(days=ACTIVE_WINDOW_DAYS + 3))], rest_confirmed=rest_confirmed,
    )
    voided = _apply_workload_fetch_failure(stale)
    assert voided['availability_status'] is None
    assert voided['operating_basis'] is None
    assert voided['data_state'] == 'incomplete'
    assert voided['inputs']['workload_fetch_failed'] is True

    clean = _apply_workload_fetch_failure(_classify([_log(REF - timedelta(days=6))]))
    assert clean['availability_status'] is None

    heavy = _apply_workload_fetch_failure(_classify([
        _log(REF - timedelta(days=1), pitches=28), _log(REF - timedelta(days=2), pitches=20),
    ]))
    assert heavy['availability_status'] not in (None, STATUS_AVAILABLE, STATUS_MONITOR)
    assert heavy['operating_basis'] == OPERATING_BASIS_PARTIAL_WORKLOAD


def test_7_recent_incomplete_gamelog_fails_closed():
    quiet = _classify([_log(REF - timedelta(days=3), pitches=None)])
    assert quiet['data_state'] == 'incomplete'
    assert quiet['availability_status'] is None
    # Observed partial workload that already crosses a threshold is a floor.
    busy = _classify([
        _log(REF - timedelta(days=1), pitches=None),
        _log(REF - timedelta(days=2), pitches=30),
        _log(REF - timedelta(days=3), pitches=25),
    ])
    assert busy['data_state'] == 'incomplete'
    assert busy['availability_status'] in {STATUS_MONITOR, STATUS_LIMITED, 'Avoid', 'Unavailable'}
    assert busy['operating_basis'] == OPERATING_BASIS_PARTIAL_WORKLOAD


def test_8_ledger_confirmed_rest_never_fabricates_a_modeled_score():
    old_score = _score(91.0)
    availability = _classify(
        [_log(REF - timedelta(days=20), pitches=40)], score=old_score, rest_confirmed=True,
    )
    # A carried 91 score would have made the arm Avoid; it is never read.
    assert availability['availability_status'] == STATUS_AVAILABLE
    assert availability['data_state'] == 'stale'
    assert any('no current workload score' in item for item in availability['limitations'])
    assert all('fatigue' not in reason.lower() for reason in availability['reasons'])
    # The Pitcher Current Read still says the modeled read is limited.
    from services.pitcher_public_labels import build_public_arm_read
    assert build_public_arm_read(availability)['key'] == 'limited_read'


# ── Team State contract (v3_phase_6) ─────────────────────────────────────────

def _fresh_clean():
    return _classify([_log(REF - timedelta(days=6), pitches=12)])


def _fresh_monitor():
    return _classify([_log(REF - timedelta(days=1), pitches=16)])


def _fresh_limited():
    return _classify([_log(REF - timedelta(days=1), pitches=27)])


def _stale(rest_confirmed=True):
    return _classify([_log(REF - timedelta(days=20))], rest_confirmed=rest_confirmed)


def test_method_version_advanced():
    assert TEAM_STATE_METHOD_VERSION == 'v3_phase_6'
    assert AVAILABILITY_METHOD_VERSION == 'availability_engine_v2'


def test_9_all_fresh_clean_team_is_fresh():
    code, evidence = _team([_fresh_clean() for _ in range(8)])
    assert code == 'operationally_stable'
    assert evidence['method_version'] == 'v3_phase_6'


def test_10_real_workload_monitor_arms_behave_under_contract_a():
    code, evidence = _team([_fresh_clean() for _ in range(4)] + [_fresh_monitor() for _ in range(5)])
    assert code == 'operationally_constrained'
    assert evidence['moderate_count'] == 5
    assert evidence['decisive_rule'] == 'residual_stretched'


def test_11_stale_only_arms_with_complete_ledger_create_no_false_strain():
    stale_team = [_fresh_clean() for _ in range(3)] + [_stale() for _ in range(7)]
    code, evidence = _team(stale_team)
    assert evidence['moderate_count'] == 0
    assert evidence['unknown_count'] == 0
    assert code == 'operationally_stable'


def test_12_too_little_trustworthy_evidence_is_never_false_fresh():
    # Five clean arms and four with no operating evidence: the unknown arms
    # could make this Stretched or Fresh, so no state is published.
    code, evidence = _team(
        [_fresh_clean() for _ in range(5)] + [_stale(rest_confirmed=False) for _ in range(4)]
    )
    assert code == 'data_limited'
    assert evidence['decisive_rule'] == 'data_limited'
    assert evidence['decisive_inputs']['gate'] == 'evidence_indeterminate'
    assert {item['limitation_id'] for item in evidence['material_limitations']} >= {
        'team_state_withheld', 'evidence_indeterminate',
    }
    # A trust gate failure still withholds first.
    code, _ = _team([_fresh_clean() for _ in range(8)], trust={**TRUST_HIGH, 'confidence': 'low'})
    assert code == 'data_limited'


def test_12b_uncertainty_that_cannot_change_the_state_does_not_withhold():
    # Nine clean arms and one unknown: Fresh in every resolution.
    code, evidence = _team([_fresh_clean() for _ in range(9)] + [_classify([])])
    assert code == 'operationally_stable'
    assert evidence['evidence_bounds']['uncertain_unknown_count'] == 1


def test_12c_uncertainty_never_decides_a_published_state():
    """A published state is the one every resolution of the unknown arms gives.

    Resolving every unknown arm as clean and as severe (Limited/Unavailable)
    brackets what the missing evidence could be. Whenever the brackets disagree
    the state is withheld; whenever a state is published, both agree with it, so
    the unknown arms did not decide it.
    """
    severe = _classify([_log(REF - timedelta(days=1), pitches=55)])
    for clean in range(0, 11):
        for moderate in range(0, 4):
            for unknown in range(1, 4):
                known = [_fresh_clean() for _ in range(clean)] + [
                    _fresh_monitor() for _ in range(moderate)]
                code, _ = _team(known + [_classify([]) for _ in range(unknown)])
                if code == 'data_limited':
                    continue
                as_clean, _ = _team(known + [_fresh_clean() for _ in range(unknown)])
                as_severe, _ = _team(known + [severe for _ in range(unknown)])
                assert code == as_clean == as_severe, (clean, moderate, unknown, code)


# ── Idle monotonicity, real new workload, real recovery ──────────────────────

SEASON_END = date(2026, 9, 27)


def _bullpen_last_week():
    """A nine-arm pen whose final appearances spread over the last week."""
    pitcher = SimpleNamespace(id=1)
    pens = []
    for index in range(9):
        days = [SEASON_END - timedelta(days=offset) for offset in (index % 7, index % 7 + 2)]
        if index < 3:
            days.append(SEASON_END - timedelta(days=index % 7 + 1))
        pens.append([_log(day, pitches=18 + index) for day in days])
    return pitcher, pens


def _team_on(ref, pens, *, rest_confirmed, emulate_v1=False, stored_scores=None):
    """Team State on ``ref`` with production's stored-score carry-forward."""
    availabilities = []
    for index, logs in enumerate(pens):
        window_logs = [log for log in logs if ref - timedelta(days=14) <= log.game_date <= ref]
        if window_logs:
            stored_scores[index] = calculate_fatigue(
                SimpleNamespace(id=index + 1),
                sorted(window_logs, key=lambda log: log.game_date, reverse=True),
                reference_date=ref,
            )
        availability = _classify(
            logs, ref=ref, score=stored_scores.get(index), rest_confirmed=rest_confirmed,
        )
        if emulate_v1 and availability['data_state'] == 'stale':
            # Engine v1: stale evidence was a low-confidence Monitor.
            availability = {**availability, 'availability_status': STATUS_MONITOR,
                            'operating_basis': OPERATING_BASIS_WORKLOAD}
        availabilities.append(availability)
    code, _evidence = _team(availabilities)
    return code


def test_13_idle_monotonicity_aging_never_worsens_team_state():
    _pitcher, pens = _bullpen_last_week()
    for rest_confirmed in (True, False):
        stored = {}
        ranks = []
        for offset in range(1, 31):
            code = _team_on(SEASON_END + timedelta(days=offset), pens,
                            rest_confirmed=rest_confirmed, stored_scores=stored)
            assert code in RANK or code == 'data_limited'
            if code in RANK:
                ranks.append(RANK[code])
        assert ranks == sorted(ranks), (rest_confirmed, ranks)
        if rest_confirmed:
            # The proven-rest pen ends Fresh and is never withheld.
            assert len(ranks) == 30 and ranks[-1] == RANK['operationally_stable']


def test_13b_regression_removal_v1_semantics_worsened_an_idle_pen():
    """The defect, reproduced: under engine v1 the same idle pen worsens at the
    14-day boundary purely because evidence aged."""
    _pitcher, pens = _bullpen_last_week()
    stored = {}
    v1 = [
        _team_on(SEASON_END + timedelta(days=offset), pens, rest_confirmed=True,
                 emulate_v1=True, stored_scores=stored)
        for offset in range(1, 31)
    ]
    v1_ranks = [RANK[code] for code in v1]
    assert v1_ranks != sorted(v1_ranks), v1
    assert v1_ranks[-1] < max(v1_ranks)


def test_14_real_new_workload_can_worsen_team_state():
    rested = [_fresh_clean() for _ in range(8)]
    worked = [_fresh_clean() for _ in range(3)] + [
        _classify([_log(REF - timedelta(days=1), pitches=36)]) for _ in range(5)
    ]
    assert RANK[_team(worked)[0]] < RANK[_team(rested)[0]]


def test_15_recovery_as_workload_leaves_windows_improves_team_state():
    heavy_day = REF - timedelta(days=1)
    pens = [[_log(heavy_day, pitches=34), _log(heavy_day - timedelta(days=1), pitches=30)]
            for _ in range(5)] + [[_log(REF - timedelta(days=9), pitches=12)] for _ in range(4)]

    def state_on(ref):
        return _team([_classify(logs, ref=ref, rest_confirmed=True) for logs in pens])[0]

    assert RANK[state_on(REF + timedelta(days=7))] > RANK[state_on(REF)]


# ── Public surfaces: On Watch counts and team-level disclosure ───────────────

def _card(name, availability, pitcher_id):
    return bullpen_board.build_card(
        name=name, pitcher_id=pitcher_id, fatigue_score=None, availability=availability,
    )


def test_16_stale_and_missing_arms_never_enter_the_on_watch_count():
    cards = [
        _card('Workload Watch', _fresh_monitor(), 1),
        _card('Proven Rest', _stale(rest_confirmed=True), 2),
        _card('Unproven Stale', _stale(rest_confirmed=False), 3),
        _card('No Record', _classify([]), 4),
    ]
    groups = {group['status']: group for group in bullpen_board.group_cards(cards)}
    assert [card['name'] for card in groups[STATUS_MONITOR]['pitchers']] == ['Workload Watch']
    assert [card['name'] for card in groups[STATUS_AVAILABLE]['pitchers']] == ['Proven Rest']
    limited = bullpen_board.evidence_limited_cards(cards)
    assert [card['name'] for card in limited] == ['No Record', 'Unproven Stale']
    assert all(card['availability_public_label'] is None for card in limited)
    context = bullpen_board.build_team_context(list(groups.values()))
    assert 'One reliever is in the On Watch group.' in context['health']['reasons']


def test_17_evidence_scope_names_the_affected_scope():
    records = [
        {'availability': _fresh_clean()},
        {'availability': _fresh_monitor()},
        {'availability': _stale(rest_confirmed=True)},
        {'availability': _stale(rest_confirmed=True)},
        {'availability': _classify([])},
    ]
    scope = author_evidence_scope(records)
    assert scope == valid_evidence_scope(scope)
    assert scope['active_bullpen_count'] == 5
    assert scope['current_workload_count'] == 2
    assert scope['ledger_confirmed_rest_count'] == 2
    assert scope['without_operating_evidence_count'] == 1
    assert scope['degraded'] is True
    assert scope['note'].startswith(
        '2 of 5 active relievers have not pitched in the last 14 days; complete game '
        'records confirm their rest'
    )
    assert '1 of 5 active relievers has incomplete current workload evidence' in scope['note']
    for forbidden in ('injur', 'health', 'hurt', 'warning', 'alert'):
        assert forbidden not in scope['note'].lower()
    clean_scope = author_evidence_scope([{'availability': _fresh_clean()}])
    assert clean_scope['note'] is None and clean_scope['degraded'] is False
    assert valid_evidence_scope({'contract': 'other'}) is None


def test_17b_team_board_v2_surfaces_the_frozen_scope_without_a_new_state():
    from services.team_board_v2 import build_team_board_v2_payload

    scope = author_evidence_scope([
        {'availability': _fresh_clean()}, {'availability': _stale(rest_confirmed=True)},
    ])
    board = {
        'team': TEAM, 'groups': [], 'evidence_limited_pitchers': [],
        'team_state': {'available': True, 'public_state': 'fresh', 'public_label': 'Fresh',
                       'summary': 's', 'data_through': '2026-10-06'},
        'evidence_scope': scope, 'freshness': {'data_through': '2026-10-06'},
    }
    payload = build_team_board_v2_payload(board)
    assert payload['evidence_scope']['ledger_confirmed_rest_count'] == 1
    status = payload['section_status']['team_state']
    assert status['status'] == 'partial'
    assert status['reason_code'] == 'team_state_evidence_scope_disclosed'
    assert status['limitations'] == [scope['note']]
    assert payload['team_state']['public_state'] == 'fresh'
    # A snapshot published before the carrier existed discloses nothing.
    board['evidence_scope'] = None
    status = build_team_board_v2_payload(board)['section_status']['team_state']
    assert status['status'] == 'available' and status['limitations'] == []


def test_evidence_limited_arms_stay_in_the_active_bullpen_list():
    from services.team_board_v2 import _active_arms

    limited = _card('No Record', _classify([]), 4)
    arms = _active_arms({'groups': [], 'evidence_limited_pitchers': [limited]})
    assert [arm['name'] for arm in arms] == ['No Record']
    assert arms[0]['availability']['status'] is None
    assert arms[0]['public_labels']['read']['key'] == 'limited_read'


# ── What Changed across the method transition ────────────────────────────────

def _snapshot(snapshot_id, method_version, public_state):
    value = {'contract': 'team_state_public_v1', 'available': True,
             'public_state': public_state, 'public_label': public_state.title(),
             'summary': 's', 'outcome': 'available', 'unavailable_message': None,
             'reason_code': None, 'data_through': '2026-10-06'}
    from services.public_serving_authority import TEAM_BOARD_PACKAGE_CONTRACT

    return SimpleNamespace(
        id=snapshot_id, data_through=date(2026, 10, 6),
        payload={'trusted_team_boards': {
            'contract': TEAM_BOARD_PACKAGE_CONTRACT, 'data_through': '2026-10-06',
            'by_team_id': {'120': {}},
            'frozen_team_state_by_team_id': {'120': {
                'contract': 'team_board_snapshot_team_state_v1', 'team_id': 120,
                'dashboard_snapshot_id': snapshot_id, 'represented_date': '2026-10-06',
                'method_version': method_version, 'value': value,
            }},
        }},
    )


def test_22_a_method_transition_is_never_a_baseball_event(monkeypatch):
    import services.team_board_snapshot_team_state as receipts
    import services.what_changed_comparison_identity as identity

    monkeypatch.setattr(identity, 'validate_snapshot_pair', lambda *args, **kwargs: None)
    old = _snapshot(4496, 'v3_phase_5', 'stretched')
    new = _snapshot(4497, 'v3_phase_6', 'fresh')
    # A v3_phase_5 receipt stays valid for its own snapshot (history kept).
    assert receipts.receipt_value(old, 120) == (True, old.payload['trusted_team_boards'][
        'frozen_team_state_by_team_id']['120']['value'])
    across = receipts.compare_exact_team_state(old, new, 120, identity=None)
    assert across['status'] == 'unavailable'
    assert across['reason_code'] == 'team_state_method_version_changed'
    assert across['event'] is None
    same_method = receipts.compare_exact_team_state(
        _snapshot(4497, 'v3_phase_6', 'stretched'), new, 120, identity=None)
    assert same_method['status'] == 'changed'
    assert same_method['event']['current_state'] == 'fresh'
    # An ungoverned method stamp is still invalid.
    bogus = _snapshot(9, 'v3_phase_4', 'fresh')
    present, value = receipts.receipt_value(bogus, 120)
    assert present is True and value['available'] is False


# ── Postseason workload and methodology copy ─────────────────────────────────

def test_23_postseason_workload_remains_counted():
    regular = _classify([_log(REF - timedelta(days=1), pitches=36, game_type='R')])
    postseason = _classify([_log(REF - timedelta(days=1), pitches=36, game_type='D')])
    assert postseason['availability_status'] == regular['availability_status']
    assert postseason['inputs']['pitches_yesterday'] == 36


METHODOLOGY = REPO_ROOT / 'frontend/src/components/methodology/Methodology.jsx'


def test_24_methodology_discloses_postseason_workload_and_differing_bases():
    text = ' '.join(METHODOLOGY.read_text(encoding='utf-8').split())
    assert 'regular-season and postseason games' in text
    assert 'a postseason outing is real bullpen work' in text
    assert 'regular-season games only' in text


def test_25_methodology_describes_actual_stale_and_missing_behavior():
    text = ' '.join(METHODOLOGY.read_text(encoding='utf-8').split())
    assert 'When the evidence is missing or stale, it withholds the read instead of guessing.' not in text
    assert 'old data is never turned into workload concern' in text
    assert 'never as On Watch' in text
    assert 'only when complete game records confirm that rest' in text
    assert 'withholds it rather than guessing' in text


def test_decision_record_exists():
    record = REPO_ROOT / 'docs/decisions/2026-10-07-evidence-quality-operating-state-separation.md'
    text = record.read_text(encoding='utf-8')
    assert 'v3_phase_6' in text and 'availability_engine_v2' in text


def test_engine_constants_are_stable_names():
    assert engine.OPERATING_BASES == {
        'workload', 'ledger_confirmed_rest', 'partial_workload',
    }
