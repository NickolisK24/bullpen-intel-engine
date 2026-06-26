"""Story Orchestrator (COIN Phase 4.5).

The final orchestration layer of COIN:

    ... -> Narrative Feed -> Story Orchestrator -> Story Package -> Story Writers

The orchestrator performs NO baseball intelligence and generates NO prose. It
reads a NarrativeFeed and decides the things a writer must never decide:

* Should a story be produced at all? (publishable + reason)
* Which writer(s) should receive it? (writer_targets)
* Where does it belong? (recommended_surface)
* What metadata travels with it?

It emits one deterministic ``StoryPackage``. Writers consume the package, not the
feed directly: ``StoryPackage.to_dict()`` is a superset of the feed payload, so
the existing writers accept a package as a drop-in (they read the feed fields and
ignore the publication metadata) — no writer code changes, and a writer never has
to ask "should I run?" because the orchestrator already answered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.narrative_feed_builder import build_narrative_feed
from utils.time import utc_now_naive


PACKAGE_VERSION = 'story_package_v1'
WRITER_VERSION = 'story_writers_v1'

PRIMARY_INSUFFICIENT = 'insufficient_context'
CONFIDENCE_LOW = 'LOW'
PRIORITY_CRITICAL = 'CRITICAL'
PRIORITY_HIGH = 'HIGH'

# ── Writer targets ────────────────────────────────────────────────────────────
WRITER_TEAM_STORY = 'team_story'
WRITER_DASHBOARD = 'dashboard'
WRITER_MORNING_BRIEF = 'morning_brief'
# Reserved for future surfaces — the package supports them, none are emitted yet.
WRITER_FUTURE_CAROUSEL = 'future_carousel'
WRITER_FUTURE_API = 'future_api'
WRITER_FUTURE_PUSH_NOTIFICATION = 'future_push_notification'

EXISTING_WRITER_TARGETS = frozenset({
    WRITER_TEAM_STORY, WRITER_DASHBOARD, WRITER_MORNING_BRIEF,
})

# ── Recommended surfaces ──────────────────────────────────────────────────────
SURFACE_DASHBOARD = 'dashboard'
SURFACE_TEAM_PAGE = 'team_page'
SURFACE_MORNING_BRIEF = 'morning_brief'
SURFACE_MULTIPLE = 'multiple'
SURFACE_NONE = 'none'

# ── Publish reasons ───────────────────────────────────────────────────────────
REASON_NO_COMPLETED_CONTEXT = 'no_completed_context'
REASON_INSUFFICIENT_CONFIDENCE = 'insufficient_confidence'
REASON_CRITICAL_NARRATIVE = 'critical_narrative'
REASON_HIGH_PRIORITY_NARRATIVE = 'high_priority_narrative'
REASON_MEETS_CONFIDENCE_THRESHOLD = 'meets_confidence_threshold'


@dataclass(frozen=True)
class StoryPackage:
    """A deterministic, publishable decision wrapped around one NarrativeFeed."""

    team_id: int | None
    game_pk: int | None
    package_version: str
    publishable: bool
    publish_reason: str
    confidence: str
    story_priority: str
    game_importance: str
    primary_story: str
    secondary_story: str | None
    writer_targets: list[str]
    recommended_surface: str
    safe_time_context: str
    headline_key: str
    summary_key: str
    narrative_feed: dict
    metadata: dict
    generated_at: Any = None

    def to_dict(self) -> dict:
        # Flatten the feed so a StoryPackage is a drop-in wherever a NarrativeFeed
        # was accepted (story writers read these fields and ignore the rest).
        payload = dict(self.narrative_feed)
        payload.update({
            'team_id': self.team_id,
            'game_pk': self.game_pk,
            'package_version': self.package_version,
            'generated_at': _isoformat(self.generated_at),
            'publishable': self.publishable,
            'publish_reason': self.publish_reason,
            'confidence': self.confidence,
            'story_priority': self.story_priority,
            'game_importance': self.game_importance,
            'primary_story': self.primary_story,
            'secondary_story': self.secondary_story,
            'writer_targets': list(self.writer_targets),
            'recommended_surface': self.recommended_surface,
            'safe_time_context': self.safe_time_context,
            'headline_key': self.headline_key,
            'summary_key': self.summary_key,
            'narrative_feed': self.narrative_feed,
            'metadata': dict(self.metadata),
        })
        return payload


def _isoformat(value):
    if value is None:
        return None
    isoformat = getattr(value, 'isoformat', None)
    return isoformat() if callable(isoformat) else value


def _feed_dict(narrative_feed) -> dict:
    if isinstance(narrative_feed, dict):
        return narrative_feed
    to_dict = getattr(narrative_feed, 'to_dict', None)
    if callable(to_dict):
        return to_dict()
    raise TypeError('Story orchestrator requires a NarrativeFeed or its dict form')


def _publish_decision(primary, confidence, priority, completed_game_context):
    """Deterministic publish gate. Returns (publishable, reason)."""
    if completed_game_context is None:
        return False, REASON_NO_COMPLETED_CONTEXT
    if confidence == CONFIDENCE_LOW or primary == PRIMARY_INSUFFICIENT:
        return False, REASON_INSUFFICIENT_CONFIDENCE
    if priority == PRIORITY_CRITICAL:
        return True, REASON_CRITICAL_NARRATIVE
    if priority == PRIORITY_HIGH:
        return True, REASON_HIGH_PRIORITY_NARRATIVE
    return True, REASON_MEETS_CONFIDENCE_THRESHOLD


def _writer_targets(publishable, priority) -> list[str]:
    if not publishable:
        return []
    targets = [WRITER_TEAM_STORY, WRITER_DASHBOARD]
    # The daily brief is reserved for the most consequential stories.
    if priority in (PRIORITY_CRITICAL, PRIORITY_HIGH):
        targets.append(WRITER_MORNING_BRIEF)
    return targets


def _recommended_surface(publishable, priority, importance) -> str:
    if not publishable:
        return SURFACE_NONE
    if priority in (PRIORITY_CRITICAL, PRIORITY_HIGH):
        return SURFACE_MULTIPLE
    if importance == 'LOW':
        return SURFACE_DASHBOARD
    return SURFACE_TEAM_PAGE


def build_story_package(
    team_id=None,
    *,
    narrative_feed=None,
    reference_date=None,
    completed_game_context=None,
    team_context=None,
    generated_at=None,
) -> StoryPackage:
    """Assemble one deterministic StoryPackage for a team.

    Reads the NarrativeFeed (built on demand, or injected for tests/pure use),
    applies the deterministic publish/target/surface rules, and packages the
    result. No baseball reasoning and no prose — only orchestration metadata.
    """
    if narrative_feed is None:
        narrative_feed = build_narrative_feed(
            team_id,
            reference_date=reference_date,
            completed_game_context=completed_game_context,
            team_context=team_context,
        )
    feed = _feed_dict(narrative_feed)

    confidence = feed.get('confidence', CONFIDENCE_LOW)
    primary = feed.get('primary_narrative', PRIMARY_INSUFFICIENT)
    priority = feed.get('story_priority', 'LOW')
    importance = feed.get('game_importance', 'LOW')
    completed = feed.get('completed_game_context')

    publishable, reason = _publish_decision(primary, confidence, priority, completed)
    targets = _writer_targets(publishable, priority)
    surface = _recommended_surface(publishable, priority, importance)

    narrative_context = feed.get('narrative_context') or {}
    metadata = {
        'story_version': PACKAGE_VERSION,
        'feed_version': feed.get('feed_version'),
        'context_version': narrative_context.get('story_version'),
        'writer_version': WRITER_VERSION,
        'generated_from': 'narrative_feed',
    }

    return StoryPackage(
        team_id=team_id if team_id is not None else feed.get('team_id'),
        game_pk=feed.get('game_pk'),
        package_version=PACKAGE_VERSION,
        publishable=publishable,
        publish_reason=reason,
        confidence=confidence,
        story_priority=priority,
        game_importance=importance,
        primary_story=primary,
        secondary_story=feed.get('secondary_narrative'),
        writer_targets=targets,
        recommended_surface=surface,
        safe_time_context=feed.get('safe_time_context', 'CURRENT_STATUS'),
        headline_key=feed.get('headline_key', PRIMARY_INSUFFICIENT),
        summary_key=feed.get('summary_key', PRIMARY_INSUFFICIENT),
        narrative_feed=feed,
        metadata=metadata,
        generated_at=generated_at or utc_now_naive(),
    )
