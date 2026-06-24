"""Digest composition engine tests (Phase D2C).

Composition + suppression only — no email is sent, nothing is scheduled, and the
output is transport-neutral. Exercises the pure compose_digest over crafted
What Changed / story inputs (no DB) and the injectable build_team_digest wrapper.
"""

import services.digest_composer as dc
from services.digest_composer import (
    CAPABILITY,
    MAX_DIGEST_CHANGES,
    SUPPRESS_CHANGES_UNAVAILABLE,
    SUPPRESS_DATA_UNAVAILABLE,
    SUPPRESS_NO_BASELINE,
    SUPPRESS_NO_MEANINGFUL_CHANGE,
    SUPPRESS_NO_TEAM,
    SUPPRESS_STALE_DATA,
    build_team_digest,
    compose_digest,
)
from services.team_changes import (
    STATE_CHANGES,
    STATE_NO_BASELINE,
    STATE_NO_CHANGES,
    STATE_STALE,
    STATE_UNAVAILABLE,
)


def _changes(state=STATE_CHANGES, *, pitcher_changes=None, team_summary='Bullpen is tightening.',
             freshness=None, team=None):
    return {
        'capability': 'what_changed_since_last_game',
        'team': team or {'team_id': 118, 'team_name': 'Kansas City Royals', 'team_abbreviation': 'KC'},
        'state': state,
        'pitcher_changes': pitcher_changes if pitcher_changes is not None else [
            {'name': 'First Arm', 'change': 'moved to unavailable'},
        ],
        'team_summary': team_summary,
        'freshness': freshness or {'data_through': '2026-06-20', 'is_current': True,
                                   'freshness_state': 'current'},
        'limitations': [],
    }


def _story(*, available=True, headline='The bullpen is getting pulled in earlier than usual',
           observation='The starters are averaging 4.1 innings over the last week.',
           story_type='coverage_pressure', trust=None):
    return {
        'team_id': 118, 'team_name': 'Kansas City Royals', 'team_abbreviation': 'KC',
        'story_available': available,
        'story_type': story_type if available else None,
        'written_story': {'headline': headline, 'observation_paragraph': observation} if available else {},
        'trust_metadata': trust or {'confidence': 'high', 'data_state': 'fresh'},
    }


# ── Meaningful change -> payload ──────────────────────────────────────────────

def test_meaningful_change_composes_payload():
    result = compose_digest(team_id=118, changes=_changes(), story=_story(),
                            frontend_base_url='https://app.example.com')
    assert result['send'] is True
    assert result['reason'] is None
    assert result['capability'] == CAPABILITY
    assert result['team_id'] == 118
    assert result['subject'] == 'Kansas City Royals bullpen: what changed'
    sections = result['sections']
    assert set(sections) == {'what_changed', 'bullpen_picture', 'team_story', 'deep_link', 'trust'}


def test_what_changed_section_carries_summary_and_changes():
    result = compose_digest(team_id=118, changes=_changes(), story=_story())
    wc = result['sections']['what_changed']
    assert wc['summary'] == 'Bullpen is tightening.'
    assert wc['change_count'] == 1
    assert wc['changes'][0]['name'] == 'First Arm'


def test_changes_are_capped_for_brevity():
    many = [{'name': f'Arm {i}', 'change': 'x'} for i in range(6)]
    result = compose_digest(team_id=118, changes=_changes(pitcher_changes=many), story=_story())
    wc = result['sections']['what_changed']
    assert len(wc['changes']) == MAX_DIGEST_CHANGES
    assert wc['change_count'] == 6


def test_team_story_included_when_available():
    result = compose_digest(team_id=118, changes=_changes(), story=_story(available=True))
    story = result['sections']['team_story']
    assert story['available'] is True
    assert story['story_type'] == 'coverage_pressure'
    assert story['headline'].startswith('The bullpen')
    assert story['beat']


def test_digest_still_sends_when_story_unavailable():
    # A meaningful change carries the digest even if no story published.
    result = compose_digest(team_id=118, changes=_changes(), story=_story(available=False))
    assert result['send'] is True
    assert result['sections']['team_story'] == {
        'available': False, 'story_type': None, 'headline': None, 'beat': None,
    }


def test_trust_and_freshness_included():
    result = compose_digest(team_id=118, changes=_changes(), story=_story())
    trust = result['sections']['trust']
    assert trust['data_through'] == '2026-06-20'
    assert trust['is_current'] is True
    assert trust['confidence'] == 'high'


def test_deep_link_uses_frontend_base_url():
    result = compose_digest(team_id=118, changes=_changes(), story=_story(),
                            frontend_base_url='https://app.example.com/')
    link = result['sections']['deep_link']['url']
    assert link == 'https://app.example.com/?team=118&source=digest'


# ── Suppression ───────────────────────────────────────────────────────────────

def test_no_changes_is_suppressed():
    result = compose_digest(team_id=118, changes=_changes(state=STATE_NO_CHANGES), story=_story())
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_NO_MEANINGFUL_CHANGE
    assert result['sections'] is None


def test_stale_or_unavailable_data_is_suppressed():
    result = compose_digest(team_id=118, changes=_changes(state=STATE_UNAVAILABLE), story=_story())
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_DATA_UNAVAILABLE


def test_missing_team_is_suppressed():
    result = compose_digest(team_id=None, changes=_changes(), story=_story())
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_NO_TEAM


def test_missing_changes_payload_is_suppressed():
    result = compose_digest(team_id=118, changes=None, story=_story())
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_CHANGES_UNAVAILABLE


def test_unknown_state_is_treated_as_no_change():
    result = compose_digest(team_id=118, changes=_changes(state='something_else'), story=_story())
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_NO_MEANINGFUL_CHANGE


# ── Determinism & provider independence ───────────────────────────────────────

def test_output_is_deterministic():
    a = compose_digest(team_id=118, changes=_changes(), story=_story(), frontend_base_url='https://x')
    b = compose_digest(team_id=118, changes=_changes(), story=_story(), frontend_base_url='https://x')
    assert a == b


def test_no_email_provider_dependency():
    src = open(dc.__file__).read()
    for term in ('email_delivery', 'auth_email', 'send_email', 'smtp', 'resend', 'requests'):
        assert term not in src, term


# ── Integration wrapper (injectable builders; no DB, no send) ─────────────────

class _Follow:
    def __init__(self, team_id, is_primary=False):
        self.team_id = team_id
        self.is_primary = is_primary


class _User:
    def __init__(self, follows):
        self.followed_teams = follows


def test_build_team_digest_resolves_primary_and_composes():
    calls = {}

    def fake_changes(team_id, freshness=None):
        calls['changes_team'] = team_id
        return _changes(team={'team_id': team_id, 'team_name': 'Test', 'team_abbreviation': 'TST'})

    def fake_story(team_id, as_of_date=None):
        calls['story_team'] = team_id
        return _story()

    user = _User([_Follow(147, is_primary=False), _Follow(118, is_primary=True)])
    result = build_team_digest(user, changes_builder=fake_changes, story_builder=fake_story,
                               frontend_base_url='https://x')
    assert result['send'] is True
    assert result['team_id'] == 118
    assert calls == {'changes_team': 118, 'story_team': 118}  # only the primary is built


def test_build_team_digest_suppressed_without_primary_team():
    def fail_builder(*a, **k):
        raise AssertionError('builders must not run without a primary team')

    result = build_team_digest(_User([]), changes_builder=fail_builder, story_builder=fail_builder)
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_NO_TEAM


def test_build_team_digest_forwards_freshness_to_changes_builder():
    # The freshness the delivery layer sources (board/published-snapshot) must
    # reach build_team_changes_payload, or it fail-closes to a stale state.
    received = {}

    def fake_changes(team_id, freshness=None):
        received['freshness'] = freshness
        return _changes(team={'team_id': team_id, 'team_name': 'Test', 'team_abbreviation': 'TST'})

    def fake_story(team_id, as_of_date=None):
        return _story()

    fresh = {'freshness_state': 'current', 'data_through': '2026-06-23', 'is_current': True}
    result = build_team_digest(_User([_Follow(118, is_primary=True)]), freshness=fresh,
                               changes_builder=fake_changes, story_builder=fake_story,
                               frontend_base_url='https://x')
    assert received['freshness'] == fresh
    assert result['send'] is True


# ── Honest suppression reasons per state (does not change send/suppress) ──────

def test_stale_state_is_suppressed_as_stale_data():
    result = compose_digest(team_id=118, changes=_changes(state=STATE_STALE), story=_story())
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_STALE_DATA


def test_no_baseline_state_is_suppressed_as_no_baseline():
    result = compose_digest(team_id=118, changes=_changes(state=STATE_NO_BASELINE), story=_story())
    assert result['send'] is False
    assert result['reason'] == SUPPRESS_NO_BASELINE
