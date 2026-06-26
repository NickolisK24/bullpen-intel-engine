"""CRC Phase 7 — the editorial roster-context family consumes Roster Authority.

The editorial system explains baseball; Roster Authority explains roster reality. Before this
phase, ``injury_context`` and ``injury_il_context`` each kept their own status sets
(``IL_STATUSES`` / ``NON_IL_INACTIVE_STATUSES`` / ``INJURED_LIST_STATUSES`` /
``INACTIVE_ROSTER_STATUSES``) to split injured-vs-otherwise-off-the-roster — a private copy of
roster truth that could drift from the authority's categories. They now read the authority's
canonical ``roster_status_category_for_status``; the IL/non-IL split is a coarsening of the
authority's off-roster categories.

These tests prove the editorial pipeline (injury context → Story → Digest, and the Today/feed
surface) consumes the authority's categories, that its roster counts reconcile with the
authority's ``category_counts`` over the same population, and that story/digest output is
unchanged (only the source of roster truth moved).
"""

from datetime import date
from types import SimpleNamespace

import pytest

import services.injury_context as injury_context_mod
import services.injury_il_context as injury_il_context_mod
from services.digest_composer import compose_digest
from services.injury_context import build_injury_context
from services.injury_il_context import (
    STATUS_GROUP_ACTIVE,
    STATUS_GROUP_INACTIVE_ROSTER,
    STATUS_GROUP_INJURED_LIST,
    STATUS_GROUP_UNKNOWN,
    build_injury_il_context_from_contexts,
    status_group_for_roster_status,
)
from services.roster_authority import (
    ROSTER_STATUS_CATEGORY_ACTIVE,
    ROSTER_STATUS_CATEGORY_INJURED_LIST,
    ROSTER_STATUS_CATEGORY_UNKNOWN,
    build_roster_authority,
    roster_status_category_for_status,
)
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_BEREAVEMENT,
    STATUS_DFA,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_OPTIONED,
    STATUS_PATERNITY,
    STATUS_RESTRICTED,
    STATUS_SUSPENDED,
    STATUS_UNKNOWN,
    classify_roster_status,
)
from services.story_intelligence_service_v1 import build_team_story
from services.story_observation_engine import TYPE_DEPTH_PRESSURE, build_team_observations
from services.team_changes import STATE_CHANGES


REF = date(2026, 6, 20)

# Every off-roster status, all as bullpen relievers so the role filter excludes nothing and
# injury context's counts line up one-for-one with the authority's off-roster categories.
_INJURED = (STATUS_IL_15, STATUS_IL_60)
_NON_IL_OFF_ROSTER = (
    STATUS_OPTIONED, STATUS_MINORS, STATUS_40_MAN_ONLY,
    STATUS_RESTRICTED, STATUS_SUSPENDED, STATUS_BEREAVEMENT, STATUS_PATERNITY,
    STATUS_DFA, STATUS_NON_ROSTER,
)


def _pitcher(pid, name, status, *, position='RP'):
    return SimpleNamespace(
        id=pid + 100000, mlb_id=pid, full_name=name, team_id=1, team_name='Team 1',
        team_abbreviation='T1', position=position, active=True,
        roster_status=status, roster_status_source='test_fixture' if status else None,
    )


def _active_record(pitcher):
    return {
        'pitcher': pitcher,
        'availability': {'roster_status': {'status': STATUS_ACTIVE, 'is_active_mlb': True}},
    }


def _authority_over(pitchers):
    """Roster Authority snapshot over the same pitchers injury context sees."""
    records = [
        {
            'pitcher_id': p.mlb_id,
            'name': p.full_name,
            'roster_status': classify_roster_status(p),
            'availability_status': None,
        }
        for p in pitchers
    ]
    return build_roster_authority(records)


def _non_il_off_roster_total(category_counts):
    return sum(
        count
        for category, count in category_counts.items()
        if category not in (
            ROSTER_STATUS_CATEGORY_ACTIVE,
            ROSTER_STATUS_CATEGORY_INJURED_LIST,
            ROSTER_STATUS_CATEGORY_UNKNOWN,
        )
    )


def _mixed_bullpen():
    """3 active relievers + every off-roster status (each a reliever) + 1 unknown."""
    actives = [_pitcher(i, f'Active {i}', STATUS_ACTIVE) for i in range(1, 4)]
    injured = [_pitcher(20 + i, f'Injured {i}', status) for i, status in enumerate(_INJURED)]
    non_il = [_pitcher(40 + i, f'OffRoster {i}', status) for i, status in enumerate(_NON_IL_OFF_ROSTER)]
    unknown = [_pitcher(90, 'Unknown Arm', STATUS_UNKNOWN)]
    return actives, injured + non_il + unknown


# ── The editorial contexts no longer keep their own roster-status sets ─────────

def test_editorial_modules_define_no_private_roster_status_sets():
    # The duplicated grouping sets are gone; the authority owns the status→category mapping.
    for name in ('IL_STATUSES', 'NON_IL_INACTIVE_STATUSES'):
        assert not hasattr(injury_context_mod, name), f'injury_context still defines {name}'
    for name in ('INJURED_LIST_STATUSES', 'INACTIVE_ROSTER_STATUSES'):
        assert not hasattr(injury_il_context_mod, name), f'injury_il_context still defines {name}'
    # Both read the authority's canonical status-code → category helper.
    assert injury_context_mod.roster_status_category_for_status is roster_status_category_for_status
    assert injury_il_context_mod.roster_status_category_for_status is roster_status_category_for_status


@pytest.mark.parametrize('status_code', [
    STATUS_ACTIVE, STATUS_IL_15, STATUS_IL_60, STATUS_OPTIONED, STATUS_MINORS,
    STATUS_40_MAN_ONLY, STATUS_RESTRICTED, STATUS_SUSPENDED, STATUS_BEREAVEMENT,
    STATUS_PATERNITY, STATUS_DFA, STATUS_NON_ROSTER, STATUS_UNKNOWN,
])
def test_injury_il_status_group_is_authority_sourced(status_code):
    # injury_il_context's group is a fixed coarsening of the authority category — injured_list
    # → injured_list group, active → active, unknown → unknown, every other off-roster category
    # → inactive_roster.
    category = roster_status_category_for_status(status_code)
    expected = {
        ROSTER_STATUS_CATEGORY_ACTIVE: STATUS_GROUP_ACTIVE,
        ROSTER_STATUS_CATEGORY_INJURED_LIST: STATUS_GROUP_INJURED_LIST,
        ROSTER_STATUS_CATEGORY_UNKNOWN: STATUS_GROUP_UNKNOWN,
    }.get(category, STATUS_GROUP_INACTIVE_ROSTER)
    assert status_group_for_roster_status({'status': status_code}) == expected


# ── Injury context counts reconcile with Roster Authority category_counts ──────

def test_injury_context_counts_match_authority_category_counts():
    actives, others = _mixed_bullpen()
    pitchers = actives + others
    injury = build_injury_context(
        pitchers, active_records=[_active_record(p) for p in actives], reference_date=REF,
    )
    authority = _authority_over(pitchers)
    category_counts = authority['category_counts']

    # IL count is exactly the injured_list category; non-IL inactive is every other off-roster
    # category; the inactive total is the authority's off-roster bucket.
    assert injury['il_bullpen_arms_count'] == category_counts[ROSTER_STATUS_CATEGORY_INJURED_LIST]
    assert injury['non_il_inactive_bullpen_arms_count'] == _non_il_off_roster_total(category_counts)
    assert injury['inactive_bullpen_arms_count'] == authority['counts']['inactive_roster_context_count']
    assert injury['active_bullpen_arms_count'] == category_counts[ROSTER_STATUS_CATEGORY_ACTIVE]


def test_injury_context_arm_status_types_follow_authority_categories():
    actives, others = _mixed_bullpen()
    injury = build_injury_context(
        actives + others, active_records=[_active_record(p) for p in actives], reference_date=REF,
    )
    # Each inactive arm carries an IL vs non-IL tag; in aggregate these tags partition exactly
    # like the authority's injured-list vs other-off-roster categories over the same arms.
    il = sum(1 for a in injury['inactive_bullpen_arms'] if a['status_type'] == 'IL')
    non_il = sum(1 for a in injury['inactive_bullpen_arms'] if a['status_type'] == 'NON_IL_INACTIVE')
    authority = _authority_over(actives + others)
    assert il == authority['category_counts'][ROSTER_STATUS_CATEGORY_INJURED_LIST]
    assert non_il == _non_il_off_roster_total(authority['category_counts'])


# ── Injury IL context counts reconcile with Roster Authority category_counts ───

def test_injury_il_context_counts_match_authority_category_counts():
    actives, others = _mixed_bullpen()
    pitchers = actives + others
    contexts = [
        {
            'pitcher': p,
            'roster_status': classify_roster_status(p),
            'eligibility': {'eligible': True},
        }
        for p in pitchers
    ]
    il_context = build_injury_il_context_from_contexts(contexts)
    authority = _authority_over(pitchers)
    category_counts = authority['category_counts']

    assert il_context['league']['injured_list_count'] == category_counts[ROSTER_STATUS_CATEGORY_INJURED_LIST]
    assert il_context['league']['inactive_count'] == _non_il_off_roster_total(category_counts)


# ── Story consumes the authority-sourced counts (counts match; output stable) ──

def _depth_pressure_team_context():
    """A team with a moderate depth-pressure shape, built from an authority-sourced context."""
    actives = [_pitcher(i, f'Active {i}', STATUS_ACTIVE) for i in range(1, 4)]
    inactives = [
        _pitcher(10, 'IL Sixty', STATUS_IL_60),
        _pitcher(11, 'IL Fifteen', STATUS_IL_15),
        _pitcher(12, 'Opt Arm', STATUS_OPTIONED),
    ]
    pitchers = actives + inactives
    injury = build_injury_context(
        pitchers, active_records=[_active_record(p) for p in actives], reference_date=REF,
    )
    team_context = {
        'team': {'team_id': 1, 'team_name': 'Team 1', 'team_abbreviation': 'T1'},
        'team_id': 1,
        'reference_date': REF.isoformat(),
        'injury_context': injury,
    }
    return team_context, _authority_over(pitchers)


def test_story_depth_pressure_observation_counts_match_authority():
    team_context, authority = _depth_pressure_team_context()
    observations = build_team_observations(team_context)
    depth = next(o for o in observations if o['type'] == TYPE_DEPTH_PRESSURE)

    category_counts = authority['category_counts']
    assert depth['cause_inputs']['il_bullpen_arms_count'] == category_counts[ROSTER_STATUS_CATEGORY_INJURED_LIST]
    assert depth['cause_inputs']['non_il_inactive_bullpen_arms_count'] == _non_il_off_roster_total(category_counts)
    assert depth['headline_inputs']['inactive_bullpen_arms_count'] == authority['counts']['inactive_roster_context_count']


def test_full_story_selected_observation_counts_match_authority():
    team_context, authority = _depth_pressure_team_context()
    story = build_team_story(1, as_of_date=REF, team_context=team_context)

    assert story['story_available'] is True
    assert story['story_type'] == 'depth_constraint'
    cause = story['selected_observation']['cause_inputs']
    category_counts = authority['category_counts']
    assert cause['il_bullpen_arms_count'] == category_counts[ROSTER_STATUS_CATEGORY_INJURED_LIST]
    assert cause['non_il_inactive_bullpen_arms_count'] == _non_il_off_roster_total(category_counts)


def test_story_output_is_stable_after_migration():
    # Golden output for a known population: the migration changed the source of roster truth,
    # not the story. Headline and the named inactive arms are exactly as before.
    team_context, _authority = _depth_pressure_team_context()
    story = build_team_story(1, as_of_date=REF, team_context=team_context)
    assert story['story_type'] == 'depth_constraint'
    assert story['written_story']['headline'] == (
        'The active bullpen is shorter than the roster page suggests'
    )
    cause_paragraph = story['written_story']['cause_paragraph']
    for name in ('IL Fifteen', 'IL Sixty', 'Opt'):
        assert name in cause_paragraph


# ── Digest carries the authority-sourced story unchanged ──────────────────────

def test_digest_carries_authority_sourced_story():
    team_context, _authority = _depth_pressure_team_context()
    story = build_team_story(1, as_of_date=REF, team_context=team_context)
    changes = {
        'state': STATE_CHANGES,
        'team': {'team_id': 1, 'team_name': 'Team 1', 'team_abbreviation': 'T1'},
        'pitcher_changes': [{'name': 'Some Arm', 'change': 'monitor'}],
        'team_summary': 'Bullpen depth is thinning.',
        'freshness': {'data_through': REF.isoformat(), 'is_current': True, 'freshness_state': 'current'},
    }
    digest = compose_digest(team_id=1, changes=changes, story=story, reference_date=REF.isoformat())

    assert digest['send'] is True
    team_story = digest['sections']['team_story']
    # The digest faithfully carries the authority-sourced story — same type, and the beat is the
    # story's narrative passed through unchanged (the digest computes no roster truth of its own).
    assert team_story['available'] is True
    assert team_story['story_type'] == 'depth_constraint'
    assert team_story['beat'] == story['written_story']['observation_paragraph'] or team_story['beat'] == story['written_story']['cause_paragraph']
    assert team_story['beat']
