"""Story Writers — translate a NarrativeFeed into human-readable baseball language.

Writers are pure translators: each consumes exactly one NarrativeFeed and makes
no baseball decisions (no engine/DB queries, no priorities, no observations, no
confidence or focus calls). New surfaces plug in by subclassing BaseStoryWriter
without touching the intelligence pipeline.
"""

from story_writers.base_story_writer import BaseStoryWriter, StoryDraft
from story_writers.team_story_writer import TeamStoryWriter
from story_writers.dashboard_story_writer import DashboardStoryWriter
from story_writers.morning_brief_writer import MorningBriefWriter

__all__ = [
    'BaseStoryWriter',
    'StoryDraft',
    'TeamStoryWriter',
    'DashboardStoryWriter',
    'MorningBriefWriter',
]
