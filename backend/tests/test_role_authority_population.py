"""
Role Authority V1 — shared population integration + diagnostic.

Verifies that role authority drives the single shared bullpen population helper
(the anti-drift layer every surface consumes), and that the read-only diagnostic
reports additions/removals/role distribution. Pure-Python: stub pitchers + an
explicit logs_by_pitcher map (no DB).
"""

from datetime import date, timedelta
from types import SimpleNamespace

from services.bullpen_population import (
    eligible_bullpen_pitcher_contexts,
    population_diagnostic,
)
from services.role_authority import ROLE_AMBIGUOUS, ROLE_RELIEVER, ROLE_UNKNOWN
from services.roster_status import STATUS_ACTIVE
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs

REF = date(2026, 6, 9)


def log(days_ago, games_started=None, innings_pitched=1.0, save=False, hold=False):
    innings_outs = parse_mlb_innings_to_outs(innings_pitched)
    return SimpleNamespace(
        game_date=REF - timedelta(days=days_ago),
        games_started=games_started,
        innings_pitched=outs_to_decimal_innings(innings_outs),
        innings_pitched_outs=innings_outs,
        save=save, hold=hold, save_situation=False,
    )


def pitcher(pid, name):
    return SimpleNamespace(id=pid, full_name=name, active=True, roster_status=STATUS_ACTIVE)


def _scenario():
    starter = pitcher(1, 'Starter Sam')
    reliever = pitcher(2, 'Reliever Rita')
    long_relief = pitcher(3, 'Longman Lou')
    swing = pitcher(4, 'Swingman Sid')
    unknown = pitcher(5, 'Unknown Uma')

    logs_by_pitcher = {
        1: [log(d, games_started=1, innings_pitched=6.0) for d in (1, 6, 11, 16, 21)],
        2: [log(d, games_started=0, innings_pitched=1.0, save=True) for d in (1, 3, 5, 7, 9)],
        3: [log(d, games_started=0, innings_pitched=3.1) for d in (2, 6, 10, 14, 18)],
        4: [log(2, games_started=1, innings_pitched=5.0),
            log(6, games_started=1, innings_pitched=5.0),
            log(9, games_started=1, innings_pitched=5.0),
            log(12, games_started=0, innings_pitched=1.0),
            log(14, games_started=0, innings_pitched=1.0),
            log(16, games_started=0, innings_pitched=1.0)],
        # Unknown: two short outings, no start data, no relief context.
        5: [log(2, games_started=None, innings_pitched=1.0),
            log(5, games_started=None, innings_pitched=1.0)],
    }
    pitchers = [starter, reliever, long_relief, swing, unknown]
    return pitchers, logs_by_pitcher


def _ids(contexts):
    return {ctx['pitcher'].id for ctx in contexts}


def test_default_population_excludes_starters_includes_relievers_and_swing():
    pitchers, lbp = _scenario()
    contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers, reference_date=REF, logs_by_pitcher=lbp, use_role_authority=True,
    )
    ids = _ids(contexts)
    assert 1 not in ids                 # Starter excluded
    assert {2, 3, 4}.issubset(ids)      # Reliever, long reliever, swingman included
    assert 5 not in ids                 # Unknown withheld by default


def test_unknown_surfaced_only_in_expanded_mode():
    pitchers, lbp = _scenario()
    contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers, reference_date=REF, logs_by_pitcher=lbp,
        use_role_authority=True, include_inactive_context=True,
    )
    ids = _ids(contexts)
    assert 5 in ids                     # Unknown surfaced for awareness
    assert 1 not in ids                 # Starter still excluded even in expanded mode


def test_swingman_carries_caveat_in_population():
    pitchers, lbp = _scenario()
    contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers, reference_date=REF, logs_by_pitcher=lbp, use_role_authority=True,
    )
    swing = next(ctx for ctx in contexts if ctx['pitcher'].id == 4)
    assert swing['eligibility']['role'] == ROLE_AMBIGUOUS
    assert swing['eligibility']['limitations']


def test_legacy_path_still_available_for_rollback():
    pitchers, lbp = _scenario()
    contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers, reference_date=REF, logs_by_pitcher=lbp, use_role_authority=False,
    )
    # Legacy innings heuristic excludes the long reliever (3+ IP reads as starter).
    assert 3 not in _ids(contexts)


def test_diagnostic_reports_additions_and_removals():
    pitchers, lbp = _scenario()
    diag = population_diagnostic(pitchers, reference_date=REF, logs_by_pitcher=lbp)
    addition_ids = {row['pitcher_id'] for row in diag['additions']}
    removal_ids = {row['pitcher_id'] for row in diag['removals']}

    # Long reliever: legacy excludes (IP heuristic), role includes → addition.
    assert 3 in addition_ids
    # Unknown: legacy includes (short relief sample), role withholds → removal.
    assert 5 in removal_ids
    assert diag['role_distribution'][ROLE_RELIEVER] >= 1
    assert diag['totals']['role_population'] >= 3


def test_cross_surface_parity_single_definition():
    # The board path and What Changed path both call this one helper, so a fixed
    # input yields one membership set — the anti-drift guarantee.
    pitchers, lbp = _scenario()
    a, _ = eligible_bullpen_pitcher_contexts(
        pitchers, reference_date=REF, logs_by_pitcher=lbp, use_role_authority=True)
    b, _ = eligible_bullpen_pitcher_contexts(
        pitchers, reference_date=REF, logs_by_pitcher=lbp, use_role_authority=True)
    assert _ids(a) == _ids(b)
