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
import services.role_authority as role_authority
from services.role_authority import (
    AMBIGUOUS_LIMITATION,
    AMBIGUOUS_START_SHARE_ELIGIBILITY_THRESHOLD,
    AMBIGUOUS_START_SHARE_MIN_KNOWN_APPEARANCES,
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    ROLE_STARTER,
    ROLE_UNKNOWN,
    classify_role,
)
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


def _case_logs(starts, relief, legacy_relief_context=False):
    flags = [1] * starts + [0] * relief
    logs = []
    relief_context_applied = False
    for offset, games_started in enumerate(flags, start=1):
        relief_entry = games_started == 0
        innings = 1.0 if (legacy_relief_context and relief_entry) else 4.0
        hold = bool(legacy_relief_context and relief_entry and not relief_context_applied)
        relief_context_applied = relief_context_applied or hold
        logs.append(log(offset, games_started=games_started, innings_pitched=innings, hold=hold))
    return logs


CUTOVER_CASES = [
    ('Sam Aldegheri', 6, 4, False, ROLE_AMBIGUOUS),
    ('Michael Soroka', 9, 1, True, ROLE_STARTER),
    ('Albert Suarez', 1, 9, False, ROLE_RELIEVER),
    ('Javier Assad', 4, 6, False, ROLE_AMBIGUOUS),
    ('Chase Petty', 4, 3, False, ROLE_AMBIGUOUS),
    ('Mike Burrows', 9, 1, True, ROLE_STARTER),
    ('Luinder Avila', 3, 7, False, ROLE_AMBIGUOUS),
    ('Justin Wrobleski', 8, 2, True, ROLE_STARTER),
    ('Roki Sasaki', 8, 2, True, ROLE_STARTER),
    ('Miles Mikolas', 4, 6, False, ROLE_AMBIGUOUS),
    ('Zack Littell', 7, 3, False, ROLE_AMBIGUOUS),
    ('Sean Manaea', 2, 8, False, ROLE_RELIEVER),
    ('Luis Castillo', 8, 2, True, ROLE_STARTER),
    ('Nick Martinez', 8, 2, True, ROLE_STARTER),
    ('Simeon Woods Richardson', 7, 3, False, ROLE_AMBIGUOUS),
    ('Erick Fedde', 5, 5, False, ROLE_AMBIGUOUS),
    ('Sean Burke', 7, 3, False, ROLE_AMBIGUOUS),
    ('Chris Paddack', 6, 4, False, ROLE_AMBIGUOUS),
    ('Ryan Gusto', 7, 3, False, ROLE_AMBIGUOUS),
]

ORACLE_STARTERS = {
    'Michael Soroka',
    'Mike Burrows',
    'Justin Wrobleski',
    'Roki Sasaki',
    'Luis Castillo',
    'Nick Martinez',
}
ORACLE_RELIEVERS = {'Albert Suarez', 'Sean Manaea'}
ORACLE_AMBIGUOUS_EXCLUDED = {
    'Ryan Gusto',
    'Sean Burke',
    'Simeon Woods Richardson',
    'Zack Littell',
    'Chris Paddack',
    'Sam Aldegheri',
}
ORACLE_AMBIGUOUS_ELIGIBLE = {
    'Chase Petty',
    'Erick Fedde',
    'Javier Assad',
    'Luinder Avila',
    'Miles Mikolas',
}


def _cutover_scenario():
    pitchers = []
    logs_by_pitcher = {}
    by_name = {}
    for pid, (name, starts, relief, legacy_relief_context, _role) in enumerate(CUTOVER_CASES, start=10):
        player = pitcher(pid, name)
        pitchers.append(player)
        by_name[name] = player
        logs_by_pitcher[pid] = _case_logs(
            starts,
            relief,
            legacy_relief_context=legacy_relief_context,
        )
    return pitchers, logs_by_pitcher, by_name


def _ids(contexts):
    return {ctx['pitcher'].id for ctx in contexts}


def _names(contexts):
    return {ctx['pitcher'].full_name for ctx in contexts}


def _start_share(logs):
    known = [getattr(log, 'games_started', None) for log in logs]
    covered = [flag for flag in known if flag is not None]
    starts = sum(1 for flag in covered if flag and flag > 0)
    return starts / len(covered), len(covered)


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
    ids = _ids(contexts)
    # The live legacy path now honors explicit gamesStarted relief flags, but
    # still leaves Role Authority disabled for mixed-role decisions.
    assert 3 in ids
    assert 4 not in ids
    assert 5 not in ids


def test_diagnostic_reports_additions_and_removals():
    pitchers, lbp = _scenario()
    diag = population_diagnostic(pitchers, reference_date=REF, logs_by_pitcher=lbp)
    addition_ids = {row['pitcher_id'] for row in diag['additions']}
    removal_ids = {row['pitcher_id'] for row in diag['removals']}

    # Swingman: Role Authority includes with a caveat; legacy still withholds.
    assert 4 in addition_ids
    # Unknown start data is withheld by both paths rather than treated as relief.
    assert 5 not in removal_ids
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


def test_role_authority_cutover_named_oracle_current_patterns():
    pitchers, lbp, by_name = _cutover_scenario()
    role_contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=True,
    )
    legacy_contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=False,
    )
    role_names = _names(role_contexts)
    legacy_names = _names(legacy_contexts)

    for name in ORACLE_STARTERS:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        assert result['role'] == ROLE_STARTER
        assert result['eligible'] is False
        assert name in legacy_names
        assert name not in role_names

    for name in ORACLE_RELIEVERS:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        assert result['role'] == ROLE_RELIEVER
        assert result['eligible'] is True
        assert name not in legacy_names
        assert name in role_names

    for name in ORACLE_AMBIGUOUS_EXCLUDED:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        share, known = _start_share(lbp[player.id])
        assert result['role'] == ROLE_AMBIGUOUS
        assert result['eligible'] is False
        assert share >= AMBIGUOUS_START_SHARE_ELIGIBILITY_THRESHOLD
        assert known >= AMBIGUOUS_START_SHARE_MIN_KNOWN_APPEARANCES
        assert name not in role_names

    for name in ORACLE_AMBIGUOUS_ELIGIBLE:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        share, known = _start_share(lbp[player.id])
        assert result['role'] == ROLE_AMBIGUOUS
        assert result['eligible'] is True
        assert share < AMBIGUOUS_START_SHARE_ELIGIBILITY_THRESHOLD
        assert known >= AMBIGUOUS_START_SHARE_MIN_KNOWN_APPEARANCES
        assert AMBIGUOUS_LIMITATION in result['limitations']
        assert name in role_names


def test_role_authority_cutover_diff_structural_sanity():
    pitchers, lbp, by_name = _cutover_scenario()
    role_contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=True,
    )
    legacy_contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=False,
    )
    role_names = _names(role_contexts)
    legacy_names = _names(legacy_contexts)

    expected_removed = {name for name, _s, _r, _legacy, role in CUTOVER_CASES if role == ROLE_STARTER}
    expected_added = ORACLE_RELIEVERS | ORACLE_AMBIGUOUS_ELIGIBLE

    assert legacy_names - role_names == expected_removed
    assert role_names - legacy_names == expected_added

    for name in expected_removed:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        assert result['role'] == ROLE_STARTER
        assert result['eligible'] is False

    for name in ORACLE_RELIEVERS:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        assert result['role'] == ROLE_RELIEVER
        assert result['eligible'] is True

    for name in ORACLE_AMBIGUOUS_ELIGIBLE:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        share, _known = _start_share(lbp[player.id])
        assert result['role'] == ROLE_AMBIGUOUS
        assert result['eligible'] is True
        assert share < AMBIGUOUS_START_SHARE_ELIGIBILITY_THRESHOLD

    for name in ORACLE_AMBIGUOUS_EXCLUDED:
        player = by_name[name]
        result = classify_role(player, lbp[player.id], reference_date=REF)
        share, _known = _start_share(lbp[player.id])
        assert result['role'] == ROLE_AMBIGUOUS
        assert result['eligible'] is False
        assert share >= AMBIGUOUS_START_SHARE_ELIGIBILITY_THRESHOLD


def test_default_population_uses_flag_and_false_restores_legacy(monkeypatch):
    pitchers, lbp, _by_name = _cutover_scenario()

    explicit_role, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=True,
    )
    explicit_legacy, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=False,
    )

    monkeypatch.setenv('ROLE_AUTHORITY_ENABLED', 'true')
    default_role, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=None,
    )
    assert _ids(default_role) == _ids(explicit_role)

    monkeypatch.setenv('ROLE_AUTHORITY_ENABLED', 'false')
    rollback_legacy, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=None,
    )
    assert _ids(rollback_legacy) == _ids(explicit_legacy)


def test_ambiguous_threshold_above_one_restores_all_ambiguous_population(monkeypatch):
    monkeypatch.setattr(
        role_authority,
        'AMBIGUOUS_START_SHARE_ELIGIBILITY_THRESHOLD',
        1.01,
    )
    pitchers, lbp, _by_name = _cutover_scenario()
    contexts, _ = eligible_bullpen_pitcher_contexts(
        pitchers,
        reference_date=REF,
        logs_by_pitcher=lbp,
        use_role_authority=True,
    )
    names = _names(contexts)
    assert ORACLE_AMBIGUOUS_EXCLUDED.issubset(names)
    assert ORACLE_AMBIGUOUS_ELIGIBLE.issubset(names)
