"""Team digest composition (Phase D2C).

Decides whether a followed-team user should receive a "what changed for your
team" digest, and if so composes a transport-neutral payload. This phase only
composes and suppresses — it never sends email, schedules a job, or reads
notification preferences. It reuses existing intelligence (What Changed Since
Last Game, the canonical team story, and freshness/trust) and invents nothing.
"""

from __future__ import annotations

from services.story_intelligence_service_v1 import build_team_story
from services.team_changes import (
    STATE_CHANGES,
    STATE_UNAVAILABLE,
    build_team_changes_payload,
)


CAPABILITY = 'team_digest_v1'

# Suppression reasons — no digest is produced.
SUPPRESS_NO_TEAM = 'no_followed_team'
SUPPRESS_CHANGES_UNAVAILABLE = 'changes_unavailable'
SUPPRESS_DATA_UNAVAILABLE = 'data_unavailable'        # stale or missing data
SUPPRESS_NO_MEANINGFUL_CHANGE = 'no_meaningful_change'

MAX_DIGEST_CHANGES = 3


def _dict(value):
    return value if isinstance(value, dict) else {}


def _suppressed(reason, *, team_id=None, team_name=None, reference_date=None):
    return {
        'capability': CAPABILITY,
        'send': False,
        'reason': reason,
        'team_id': team_id,
        'team_name': team_name,
        'reference_date': reference_date,
        'subject': None,
        'sections': None,
    }


def _team_identity(changes, story, fallback_team_id):
    team = _dict(changes.get('team'))
    team_id = team.get('team_id') or story.get('team_id') or fallback_team_id
    team_name = team.get('team_name') or story.get('team_name')
    team_abbreviation = team.get('team_abbreviation') or story.get('team_abbreviation')
    return team_id, team_name, team_abbreviation


def _story_field(story, *keys):
    written = _dict(story.get('written_story'))
    for key in keys:
        if story.get(key):
            return story.get(key)
        if written.get(key):
            return written.get(key)
    return None


def _deep_link(frontend_base_url, team_id):
    base = (frontend_base_url or '').rstrip('/')
    return f'{base}/?team={team_id}&source=digest'


def _trust(changes, story):
    freshness = _dict(changes.get('freshness'))
    trust_meta = _dict(story.get('trust_metadata'))
    return {
        'data_through': freshness.get('data_through'),
        'is_current': bool(freshness.get('is_current') is True),
        'confidence': trust_meta.get('confidence'),
        'data_state': trust_meta.get('data_state') or freshness.get('freshness_state'),
    }


def compose_digest(*, team_id, changes, story=None, reference_date=None, frontend_base_url=None):
    """Compose a digest payload for one team, or a suppression decision.

    Pure over its inputs (no DB, no email, no scheduler): given the team's What
    Changed payload and canonical story, returns either a transport-neutral
    digest payload (send=True) or a suppression decision (send=False, reason).
    """
    if team_id is None:
        return _suppressed(SUPPRESS_NO_TEAM, reference_date=reference_date)
    if not isinstance(changes, dict):
        return _suppressed(SUPPRESS_CHANGES_UNAVAILABLE, team_id=team_id, reference_date=reference_date)

    story = _dict(story)
    resolved_id, team_name, team_abbr = _team_identity(changes, story, team_id)
    state = changes.get('state')

    # Suppress: stale/missing data, then no meaningful change.
    if state == STATE_UNAVAILABLE:
        return _suppressed(SUPPRESS_DATA_UNAVAILABLE, team_id=resolved_id,
                           team_name=team_name, reference_date=reference_date)
    if state != STATE_CHANGES:
        return _suppressed(SUPPRESS_NO_MEANINGFUL_CHANGE, team_id=resolved_id,
                           team_name=team_name, reference_date=reference_date)

    pitcher_changes = [c for c in (changes.get('pitcher_changes') or []) if isinstance(c, dict)]
    team_summary = changes.get('team_summary')

    story_available = bool(story.get('story_available') is True)
    story_headline = _story_field(story, 'headline')
    story_beat = _story_field(story, 'observation', 'observation_paragraph', 'cause', 'cause_paragraph')
    display_name = team_name or (f'Team {resolved_id}' if resolved_id is not None else 'Your team')

    return {
        'capability': CAPABILITY,
        'send': True,
        'reason': None,
        'team_id': resolved_id,
        'team_name': team_name,
        'team_abbreviation': team_abbr,
        'reference_date': reference_date,
        'subject': f'{display_name} bullpen: what changed',
        'sections': {
            'what_changed': {
                'summary': team_summary,
                'changes': pitcher_changes[:MAX_DIGEST_CHANGES],
                'change_count': len(pitcher_changes),
            },
            'bullpen_picture': {
                'headline': story_headline or team_summary,
            },
            'team_story': {
                'available': story_available,
                'story_type': story.get('story_type') if story_available else None,
                'headline': story_headline if story_available else None,
                'beat': story_beat if story_available else None,
            },
            'deep_link': {
                'url': _deep_link(frontend_base_url, resolved_id),
                'label': f"See {display_name}'s bullpen",
            },
            'trust': _trust(changes, story),
        },
        'limitations': list(changes.get('limitations') or []),
    }


def _primary_team_id(user):
    for follow in (getattr(user, 'followed_teams', None) or []):
        if getattr(follow, 'is_primary', False):
            return follow.team_id
    return None


def build_team_digest(
    user,
    *,
    reference_date=None,
    freshness=None,
    frontend_base_url=None,
    changes_builder=build_team_changes_payload,
    story_builder=build_team_story,
):
    """Resolve a user's primary team and compose its digest (integration wrapper).

    The content builders are injectable for testing; the defaults call the real
    services. This wrapper performs no sending and no scheduling.
    """
    team_id = _primary_team_id(user)
    if team_id is None:
        return _suppressed(SUPPRESS_NO_TEAM, reference_date=reference_date)
    changes = changes_builder(team_id, freshness=freshness)
    story = story_builder(team_id, as_of_date=reference_date)
    return compose_digest(
        team_id=team_id,
        changes=changes,
        story=story,
        reference_date=reference_date,
        frontend_base_url=frontend_base_url,
    )
