"""COIN internal story inspection (manual, read-only).

An operator-facing preview of the COIN story chain for one team:

    build StoryPackage (orchestrator) -> render existing Story Writers

It exists so a human can see what COIN *would* publish — the package decision
plus the rendered drafts — without exposing anything through the public API or
frontend, and without mutating data. It builds the package through the
orchestrator (which reads the latest CompletedGameContext and the bullpen
intelligence), then renders the existing writers, respecting publishability and
the orchestrator's writer_targets by default.

Nothing here writes to the database, fetches MLB data, publishes, or alters
sync. Unpublishable packages render no drafts unless ``include_unpublishable`` is
explicitly set, in which case the drafts are clearly flagged as internal preview.
"""

from __future__ import annotations

from story_orchestrator import (
    StoryPackage,
    WRITER_DASHBOARD,
    WRITER_MORNING_BRIEF,
    WRITER_TEAM_STORY,
    build_story_package,
)
from story_writers import (
    DashboardStoryWriter,
    MorningBriefWriter,
    TeamStoryWriter,
)


WRITER_ALL = 'all'

# Only the existing writers — no new writer types are introduced here.
KNOWN_WRITERS = {
    WRITER_TEAM_STORY: TeamStoryWriter,
    WRITER_DASHBOARD: DashboardStoryWriter,
    WRITER_MORNING_BRIEF: MorningBriefWriter,
}


def _candidate_writer_names(package: StoryPackage, writer: str,
                            include_unpublishable: bool) -> list[str]:
    """Which writers to render, respecting writer_targets unless overridden."""
    if writer == WRITER_ALL:
        if package.writer_targets:
            return list(package.writer_targets)
        # No targets (e.g. unpublishable): only the explicit override renders,
        # and then every existing writer is shown as an internal preview.
        return list(KNOWN_WRITERS) if include_unpublishable else []

    if writer in package.writer_targets:
        return [writer]
    # A writer outside the targets renders only under explicit override.
    return [writer] if include_unpublishable else []


def _render_draft(package: StoryPackage, name: str) -> dict:
    # Writers consume the StoryPackage as a drop-in (its to_dict is a feed superset).
    draft = KNOWN_WRITERS[name](package).write()
    is_internal_preview = not (package.publishable and name in package.writer_targets)
    return {
        'writer': draft.writer,
        'headline': draft.headline,
        'body': draft.body,
        'observations': list(draft.observations),
        'evidence': list(draft.evidence),
        'text': draft.text,
        'rendered_text': draft.rendered_text,
        'metadata': draft.to_dict(),
        'is_internal_preview': is_internal_preview,
    }


def inspect_team_story(
    team_id,
    *,
    app=None,
    reference_date=None,
    writer=WRITER_ALL,
    include_unpublishable=False,
    narrative_feed=None,
    completed_game_context=None,
    team_context=None,
) -> dict:
    """Build a StoryPackage for a team and render the allowed writers.

    Read-only. ``app`` (a Flask app) wraps the read in an app context for the
    real DB path; tests may inject ``narrative_feed`` / ``completed_game_context``
    / ``team_context`` and omit ``app`` to run purely. ``writer`` is one of the
    known writer names or ``'all'``; an unknown name raises ``ValueError``.
    """
    if writer != WRITER_ALL and writer not in KNOWN_WRITERS:
        raise ValueError(
            f'unknown writer {writer!r}; choose one of '
            f'{sorted(KNOWN_WRITERS)} or {WRITER_ALL!r}'
        )

    def _run() -> dict:
        package = build_story_package(
            team_id,
            narrative_feed=narrative_feed,
            reference_date=reference_date,
            completed_game_context=completed_game_context,
            team_context=team_context,
        )
        names = _candidate_writer_names(package, writer, include_unpublishable)
        drafts = [_render_draft(package, name) for name in names]
        return {
            'team_id': package.team_id,
            'game_pk': package.game_pk,
            'publishable': package.publishable,
            'publish_reason': package.publish_reason,
            'confidence': package.confidence,
            'story_priority': package.story_priority,
            'game_importance': package.game_importance,
            'recommended_surface': package.recommended_surface,
            'safe_time_context': package.safe_time_context,
            'writer_targets': list(package.writer_targets),
            'writer_filter': writer,
            'include_unpublishable': bool(include_unpublishable),
            'package': package.to_dict(),
            'drafts': drafts,
        }

    if app is not None:
        with app.app_context():
            return _run()
    return _run()
