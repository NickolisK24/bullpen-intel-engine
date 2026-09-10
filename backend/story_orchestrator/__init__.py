"""Story Orchestrator — decide whether/where a story runs and package it.

The orchestrator turns a NarrativeFeed into a deterministic StoryPackage: the
publish decision, writer targets, recommended surface, and metadata. It performs
no baseball intelligence and writes no prose; Story Writers consume the package.
"""

from story_orchestrator.story_orchestrator import (
    EXISTING_WRITER_TARGETS,
    PACKAGE_VERSION,
    REASON_CRITICAL_NARRATIVE,
    REASON_HIGH_PRIORITY_NARRATIVE,
    REASON_INSUFFICIENT_CONFIDENCE,
    REASON_MEETS_CONFIDENCE_THRESHOLD,
    REASON_NO_COMPLETED_CONTEXT,
    SURFACE_DASHBOARD,
    SURFACE_MORNING_BRIEF,
    SURFACE_MULTIPLE,
    SURFACE_NONE,
    SURFACE_TEAM_PAGE,
    StoryPackage,
    WRITER_DASHBOARD,
    WRITER_FUTURE_API,
    WRITER_FUTURE_CAROUSEL,
    WRITER_FUTURE_PUSH_NOTIFICATION,
    WRITER_MORNING_BRIEF,
    WRITER_TEAM_STORY,
    WRITER_VERSION,
    build_story_package,
)

__all__ = [
    'build_story_package',
    'StoryPackage',
    'PACKAGE_VERSION',
    'WRITER_VERSION',
    'EXISTING_WRITER_TARGETS',
    'WRITER_TEAM_STORY',
    'WRITER_DASHBOARD',
    'WRITER_MORNING_BRIEF',
    'WRITER_FUTURE_CAROUSEL',
    'WRITER_FUTURE_API',
    'WRITER_FUTURE_PUSH_NOTIFICATION',
    'SURFACE_DASHBOARD',
    'SURFACE_TEAM_PAGE',
    'SURFACE_MORNING_BRIEF',
    'SURFACE_MULTIPLE',
    'SURFACE_NONE',
    'REASON_NO_COMPLETED_CONTEXT',
    'REASON_INSUFFICIENT_CONFIDENCE',
    'REASON_CRITICAL_NARRATIVE',
    'REASON_HIGH_PRIORITY_NARRATIVE',
    'REASON_MEETS_CONFIDENCE_THRESHOLD',
]
