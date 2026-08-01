"""Source-shape field ownership, and why two lanes disagreed about `balls`.

Production evidence (game 824488, pitcher 668716, field `balls`, recurring
across a postgame and a daily shadow cycle at the same source revision and the
same plan fingerprint) exposed a structural property nothing had declared:

    a governed optional statistic is compared only when the SOURCE DICT
    carries its key.

``correctable_fields`` appends each optional stat on presence, which is correct
— an absent optional stat must never be rewritten to a default. But the daily
legacy writer reads the player game-log split and the game-driven lane reads the
completed-game box score, so a field one endpoint omits is never compared and
never corrected *by that lane*. It is not found equal. It is never looked at.

These tests own that property and the diagnostic that makes it visible. They
prove the rule, not the production row: no game or pitcher identifier from
production appears in any assertion about behaviour.
"""

from datetime import date

import pytest

from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity


GAME_PK = 970001
SLATE = date(2026, 6, 20)


class _Row:
    """A stored appearance row, as the planner reads one."""

    def __init__(self, **fields):
        defaults = {
            'game_date': SLATE, 'game_type': 'R', 'innings_pitched_outs': 3,
            'innings_pitched': 1.0, 'pitches_thrown': 14, 'strikes': 9,
            'hits_allowed': 0, 'runs_allowed': 0, 'earned_runs': 0, 'walks': 0,
            'strikeouts': 1, 'home_runs_allowed': 0, 'games_started': 0,
            'balls': 5, 'batters_faced': 3, 'opponent': None,
            'opponent_abbreviation': None, 'appearance_team_id': None,
            'appearance_team_source': None, 'appearance_team_status': None,
            'appearance_team_reason': None,
        }
        defaults.update(fields)
        for key, value in defaults.items():
            setattr(self, key, value)


def _values(**overrides):
    values = {
        'mlb_game_pk': GAME_PK, 'game_date': SLATE, 'game_type': 'R',
        'innings_pitched_outs': 3, 'innings_pitched': 1.0,
        'pitches_thrown': 14, 'strikes': 9, 'hits_allowed': 0,
        'runs_allowed': 0, 'earned_runs': 0, 'walks': 0, 'strikeouts': 1,
        'home_runs_allowed': 0, 'games_started': 0, 'balls': 5,
        'batters_faced': 3,
    }
    values.update(overrides)
    return values


def _boxscore_stats(**overrides):
    """The completed-game box-score shape: carries balls, strikes, pitches."""
    stats = {
        'inningsPitched': '1.0', 'strikes': 9, 'hits': 0, 'runs': 0,
        'earnedRuns': 0, 'baseOnBalls': 0, 'strikeOuts': 1, 'homeRuns': 0,
        'numberOfPitches': 14, 'balls': 5, 'battersFaced': 3,
    }
    stats.update(overrides)
    return stats


def _split_stats(*, with_balls=False, **overrides):
    """The player game-log split shape, parameterised on whether it carries
    `balls` — which is exactly the unresolved question."""
    stats = {
        'inningsPitched': '1.0', 'strikes': 9, 'hits': 0, 'runs': 0,
        'earnedRuns': 0, 'baseOnBalls': 0, 'strikeOuts': 1, 'homeRuns': 0,
        'numberOfPitches': 14, 'battersFaced': 3,
    }
    if with_balls:
        stats['balls'] = 5
    stats.update(overrides)
    return stats


def _plan(existing, values, stats):
    return reconciliation.plan_row(
        existing=existing, values=values, stats=stats, game_pk=GAME_PK,
        pitcher_mlb_id=970100, local_pitcher_id=1,
        identity_plan={'action': pitcher_identity.ACTION_UNCHANGED},
    )


# ── The rule: comparability follows the source shape ────────────────────────


def test_a_source_carrying_the_key_can_compare_the_field():
    fields = reconciliation.correctable_fields(
        _values(), _boxscore_stats(), include_leverage_index=False,
    )
    assert 'balls' in fields


def test_a_source_omitting_the_key_cannot_compare_the_field():
    fields = reconciliation.correctable_fields(
        _values(), _split_stats(with_balls=False), include_leverage_index=False,
    )
    assert 'balls' not in fields


def test_omission_is_not_agreement(caplog):
    """The distinction the production artifact turned on.

    A lane reading a source without the key reports no difference — not
    because the values match, but because it never compared them.
    """
    stored = _Row(balls=99)

    box_plan = _plan(stored, _values(balls=5), _boxscore_stats(balls=5))
    split_plan = _plan(
        stored, _values(balls=5), _split_stats(with_balls=False),
    )

    assert box_plan['action'] == reconciliation.ACTION_UPDATE
    assert 'balls' in box_plan['changed_fields']

    assert split_plan['action'] == reconciliation.ACTION_UNCHANGED
    assert 'balls' not in split_plan['changed_fields']
    # ...and it says so, rather than looking like agreement.
    assert 'balls' in split_plan['uncomparable_fields']


def test_a_source_that_can_compare_reports_no_uncomparable_field():
    plan = _plan(_Row(), _values(), _boxscore_stats())
    assert 'balls' not in plan['uncomparable_fields']


def test_the_uncomparable_set_covers_every_source_optional_field():
    """A future optional stat must not slip in without this visibility."""
    bare = {
        'inningsPitched': '1.0', 'strikes': 9, 'hits': 0, 'runs': 0,
        'earnedRuns': 0, 'baseOnBalls': 0, 'strikeOuts': 1, 'homeRuns': 0,
    }
    values = _values(
        games_finished=1, inherited_runners=0, inherited_runners_scored=0,
        save_situation=False, hold=False, blown_save=False, win=False,
        loss=False, save=False,
    )
    plan = _plan(_Row(), values, bare)
    for field in ('balls', 'batters_faced', 'games_finished'):
        assert field in plan['uncomparable_fields']


def test_a_field_absent_from_the_values_is_not_reported_uncomparable():
    """Only fields the canonical builder actually produced are in scope."""
    plan = _plan(_Row(), _values(), _boxscore_stats())
    assert 'leverage_index' not in plan['uncomparable_fields']


def test_the_uncomparable_list_is_deterministic():
    first = _plan(_Row(), _values(), _split_stats(with_balls=False))
    second = _plan(_Row(), _values(), _split_stats(with_balls=False))
    assert first['uncomparable_fields'] == second['uncomparable_fields']
    assert first['uncomparable_fields'] == sorted(first['uncomparable_fields'])


# ── Source-semantics fixtures ───────────────────────────────────────────────


def test_both_sources_carrying_the_field_and_agreeing_is_unchanged():
    stored = _Row(balls=5)
    for stats in (_boxscore_stats(balls=5), _split_stats(with_balls=True)):
        plan = _plan(stored, _values(balls=5), stats)
        assert plan['action'] == reconciliation.ACTION_UNCHANGED


def test_sources_disagreeing_on_the_field_produces_one_update():
    stored = _Row(balls=5)
    plan = _plan(stored, _values(balls=7), _boxscore_stats(balls=7))
    assert plan['action'] == reconciliation.ACTION_UPDATE
    assert plan['changed_fields'] == ['balls']


def test_a_null_stored_value_against_an_authoritative_source_is_an_update():
    stored = _Row(balls=None)
    plan = _plan(stored, _values(balls=5), _boxscore_stats(balls=5))
    assert plan['action'] == reconciliation.ACTION_UPDATE
    assert plan['changed_fields'] == ['balls']


def test_an_explicitly_null_source_value_preserves_the_stored_value():
    """The presence rule is stricter than key-presence.

    ``stat_key_present`` requires the key AND a value that is not None or the
    empty string, so a source sending ``balls: null`` is treated exactly like a
    source that omits it: the field is not compared and the stored value is
    preserved rather than clobbered to null. Worth pinning, because "the key
    was there" is the intuitive reading and it is wrong.
    """
    stored = _Row(balls=5)
    plan = _plan(stored, _values(balls=None), _boxscore_stats(balls=None))
    assert plan['action'] == reconciliation.ACTION_UNCHANGED
    assert 'balls' in plan['uncomparable_fields']


@pytest.mark.parametrize('empty', [None, ''])
def test_an_empty_source_value_is_treated_as_absent(empty):
    stored = _Row(balls=5)
    plan = _plan(stored, _values(balls=None), _boxscore_stats(balls=empty))
    assert plan['action'] == reconciliation.ACTION_UNCHANGED
    assert 'balls' in plan['uncomparable_fields']


def test_an_absent_source_key_leaves_a_stored_value_untouched():
    stored = _Row(balls=5)
    plan = _plan(stored, _values(balls=None), _split_stats(with_balls=False))
    assert plan['action'] == reconciliation.ACTION_UNCHANGED
    assert 'balls' in plan['uncomparable_fields']


def test_pitches_minus_strikes_equalling_balls_is_not_relied_upon():
    """No derivation is performed anywhere. If it were, this would pass by
    accident on consistent inputs and fail on real ones."""
    stored = _Row(balls=None, pitches_thrown=14, strikes=9)
    plan = _plan(
        stored, _values(balls=None),
        _split_stats(with_balls=False, numberOfPitches=14, strikes=9),
    )
    # 14 - 9 = 5, and nothing proposes 5.
    assert plan['action'] == reconciliation.ACTION_UNCHANGED
    assert plan['changed_fields'] == []


def test_a_strikes_correction_does_not_drag_balls_with_it():
    """If balls were derived from pitches and strikes, correcting strikes
    would silently move balls. It does not: each governed field is compared
    against its own source value."""
    stored = _Row(balls=5, pitches_thrown=14, strikes=9)
    plan = _plan(
        stored,
        _values(balls=5, strikes=4),
        _boxscore_stats(balls=5, strikes=4),
    )
    assert plan['changed_fields'] == ['strikes']
    assert 'balls' not in plan['changed_fields']


def test_no_derivation_helper_exists_for_the_field():
    """A derivation added later must be a deliberate, reviewed decision."""
    import inspect

    source = inspect.getsource(reconciliation)
    for pattern in (
        'pitches_thrown - strikes', 'pitches - strikes',
        "values['pitches_thrown'] -",
    ):
        assert pattern not in source


# ── The field is a statistical correction, not something else ───────────────


def test_the_field_is_governed_as_a_statistical_correction():
    assert reconciliation.field_category('balls') == (
        reconciliation.CATEGORY_STATISTICAL_CORRECTION
    )


def test_a_difference_classifies_as_a_statistical_correction():
    stored = _Row(balls=5)
    plan = _plan(stored, _values(balls=7), _boxscore_stats(balls=7))
    assert plan['difference_classifications'] == [
        reconciliation.DIFFERENCE_STATISTICAL
    ]


def test_the_field_is_published_evidence():
    assert 'balls' in reconciliation.PUBLISHED_EVIDENCE_FIELDS


def test_a_difference_does_not_touch_integer_outs_authority():
    stored = _Row(balls=5, innings_pitched_outs=3)
    plan = _plan(stored, _values(balls=7), _boxscore_stats(balls=7))
    assert 'innings_pitched_outs' not in plan['changed_fields']
    assert 'innings_pitched' not in plan['changed_fields']


def test_a_difference_does_not_touch_pitcher_identity():
    stored = _Row(balls=5)
    plan = _plan(stored, _values(balls=7), _boxscore_stats(balls=7))
    assert plan['pitcher_identity_action'] == pitcher_identity.ACTION_UNCHANGED


def test_a_difference_does_not_touch_appearance_team_authority():
    stored = _Row(balls=5)
    plan = _plan(stored, _values(balls=7), _boxscore_stats(balls=7))
    assert plan['appearance_team_reason'] is None


# ── The correction remains idempotent ───────────────────────────────────────


def test_applying_the_target_makes_the_replay_unchanged():
    stored = _Row(balls=5)
    first = _plan(stored, _values(balls=7), _boxscore_stats(balls=7))
    assert first['action'] == reconciliation.ACTION_UPDATE

    stored.balls = 7  # what a writer applying that plan would store
    replay = _plan(stored, _values(balls=7), _boxscore_stats(balls=7))
    assert replay['action'] == reconciliation.ACTION_UNCHANGED


# ── The audit tool is read-only by construction ─────────────────────────────


def test_the_audit_tool_reports_only_the_fields_needed_to_interpret_the_stat():
    from scripts import inspect_gamelog_field_authority as audit

    assert audit.REPORTABLE_VALUE_FIELDS == ('balls', 'strikes', 'pitches_thrown')
    assert audit.REPORTABLE_SOURCE_KEYS == ('balls', 'strikes', 'numberOfPitches')


def test_the_audit_tool_pins_the_lane_off_before_importing_anything():
    import pathlib

    from scripts import inspect_gamelog_field_authority as audit

    text = pathlib.Path(audit.__file__).read_text(encoding='utf-8')
    mode_at = text.index("os.environ['GAME_DRIVEN_INGESTION_MODE'] = 'off'")
    app_at = text.index('from app import app')
    assert mode_at < app_at


def test_the_audit_tool_opens_a_read_only_transaction_and_probes_it():
    import pathlib

    from scripts import inspect_gamelog_field_authority as audit

    text = pathlib.Path(audit.__file__).read_text(encoding='utf-8')
    assert 'SET TRANSACTION READ ONLY' in text
    assert 'write_probe_refused' in text
    assert 'db.session.rollback()' in text


def test_the_audit_tool_performs_no_write_or_publication():
    import pathlib

    from scripts import inspect_gamelog_field_authority as audit

    text = pathlib.Path(audit.__file__).read_text(encoding='utf-8')
    for forbidden in (
        'db.session.commit()', 'db.session.add(', 'record_failure(',
        'publish_dashboard_snapshot', 'GameIngestionWorkItem(',
        'run_game_driven_ingestion',
    ):
        assert forbidden not in text, f'the audit tool must not {forbidden!r}'


def test_the_audit_tool_uses_the_canonical_planner_not_a_comparator():
    import pathlib

    from scripts import inspect_gamelog_field_authority as audit

    text = pathlib.Path(audit.__file__).read_text(encoding='utf-8')
    assert 'reconciliation.plan_row(' in text
    assert '_game_log_values_from_stats(' in text


def test_the_audit_tool_hardcodes_no_production_identifier():
    import pathlib

    from scripts import inspect_gamelog_field_authority as audit

    text = pathlib.Path(audit.__file__).read_text(encoding='utf-8')
    # The production incident may be named in the docstring for context; it
    # must never be a default or a branch condition.
    body = text.split('"""', 2)[-1]
    assert '824488' not in body
    assert '668716' not in body


def test_no_production_identifier_reached_production_logic():
    import pathlib

    for module in (
        'backend/services/sync.py',
        'backend/services/game_log_reconciliation.py',
        'backend/services/game_driven_ingestion.py',
        'backend/services/game_driven_realization.py',
        'backend/scripts/validate_game_driven_shadow_cycle.py',
    ):
        text = pathlib.Path(
            pathlib.Path(__file__).resolve().parents[2] / module
        ).read_text(encoding='utf-8')
        assert '824488' not in text
        assert '668716' not in text


# ── The correction vocabulary was not widened to make shadow green ──────────


def test_the_field_was_not_added_to_or_removed_from_the_vocabulary():
    """Neither silencing the difference nor blessing it — the audit is
    unresolved, so the governed vocabulary is untouched."""
    assert ('balls', ('balls',)) in reconciliation.OPTIONAL_INT_STAT_FIELDS
    assert 'balls' in reconciliation.STATISTICAL_FIELDS


def test_the_required_correction_keys_are_unchanged():
    assert reconciliation.REQUIRED_CORRECTION_STAT_KEYS == (
        'inningsPitched', 'strikes', 'hits', 'runs', 'earnedRuns',
        'baseOnBalls', 'strikeOuts', 'homeRuns',
    )


@pytest.mark.parametrize('version,expected', [
    ('RECONCILIATION_PLAN_VERSION', '3'),
    ('PARITY_CONTRACT_VERSION', '4'),
    ('INNINGS_SEMANTICS_VERSION', '2'),
    ('COMPLETE_PLAN_VERSION', '1'),
])
def test_no_contract_version_moved(version, expected):
    assert getattr(reconciliation, version) == expected
