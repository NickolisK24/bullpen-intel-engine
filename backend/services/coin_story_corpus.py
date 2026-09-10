"""COIN internal review corpus generator (manual, read-only).

Builds a private review corpus across several teams so BaseballOS story quality
can be evaluated before any API/frontend wiring. It is a thin batch wrapper over
the existing internal inspection path (``coin_story_inspection.inspect_team_story``):
for each team it collects the StoryPackage decision and the rendered drafts, then
shapes them into a JSON artifact (and an optional Markdown one for easy reading).

It reads only existing COIN inspection/orchestrator/writer outputs: no database
writes, no MLB fetches, no backfill, no publishing, no API/frontend changes. The
only files it produces are local review artifacts written by the caller/script.
Per-team failures are captured as an error entry and never abort the whole
corpus (unless ``strict`` is set).
"""

from __future__ import annotations

import json

from services.coin_story_inspection import inspect_team_story
from utils.time import utc_now_naive


# Initial target teams for internal review.
DEFAULT_TEAM_IDS = [137, 133, 139, 147]
TEAM_LABELS = {
    137: 'Giants',
    133: 'Athletics',
    139: 'Rays',
    147: 'Yankees',
}

# Ordered writers for stable Markdown rendering.
_MARKDOWN_WRITERS = (
    ('team_story', 'Team Story'),
    ('dashboard', 'Dashboard'),
    ('morning_brief', 'Morning Brief'),
)


def _isoformat(value):
    if value is None:
        return None
    isoformat = getattr(value, 'isoformat', None)
    return isoformat() if callable(isoformat) else value


def _entry_from_inspection(team_id, result) -> dict:
    return {
        'team_id': result.get('team_id', team_id),
        'game_pk': result.get('game_pk'),
        'publishable': result.get('publishable'),
        'publish_reason': result.get('publish_reason'),
        'confidence': result.get('confidence'),
        'story_priority': result.get('story_priority'),
        'game_importance': result.get('game_importance'),
        'recommended_surface': result.get('recommended_surface'),
        'safe_time_context': result.get('safe_time_context'),
        'primary_story': (result.get('package') or {}).get('primary_story'),
        'writer_targets': result.get('writer_targets', []),
        'package': result.get('package'),
        'drafts': result.get('drafts', []),
        'error': None,
    }


def _error_entry(team_id, message) -> dict:
    return {
        'team_id': team_id,
        'game_pk': None,
        'publishable': None,
        'publish_reason': None,
        'confidence': None,
        'story_priority': None,
        'game_importance': None,
        'recommended_surface': None,
        'safe_time_context': None,
        'primary_story': None,
        'writer_targets': [],
        'package': None,
        'drafts': [],
        'error': message,
    }


def generate_corpus(
    team_ids=None,
    *,
    app=None,
    reference_date=None,
    writer='all',
    include_unpublishable=False,
    strict=False,
    generated_at=None,
    inspect_fn=inspect_team_story,
    seeded=False,
) -> dict:
    """Build the review corpus for ``team_ids`` (defaults to the four target teams).

    Reuses the inspection path per team. Per-team failures become error entries
    and the corpus continues, unless ``strict`` re-raises. ``inspect_fn`` is
    injectable for tests; ``generated_at`` is injectable for deterministic output.

    When ``seeded`` is True the corpus is built from the deterministic review
    fixtures instead of the database/MLB: the team list and inspection function
    come from ``coin_seeded_fixtures``, every entry is tagged with its
    fixture_name / expected_primary_story, and the corpus carries a
    ``mode = SEEDED_FIXTURE_REVIEW`` marker. The non-seeded shape is unchanged.
    """
    meta_fn = None
    if seeded:
        from services.coin_seeded_fixtures import (
            SEEDED_TEAM_IDS,
            build_seeded_inspect_fn,
            fixture_meta,
        )
        if team_ids is None:
            team_ids = list(SEEDED_TEAM_IDS)
        if inspect_fn is inspect_team_story:
            inspect_fn = build_seeded_inspect_fn()
        meta_fn = fixture_meta

    team_ids = list(team_ids) if team_ids else list(DEFAULT_TEAM_IDS)

    entries = []
    for team_id in team_ids:
        try:
            result = inspect_fn(
                team_id,
                app=app,
                reference_date=reference_date,
                writer=writer,
                include_unpublishable=include_unpublishable,
            )
            entry = _entry_from_inspection(team_id, result)
        except Exception as exc:  # noqa: BLE001 — per-team fail-closed
            if strict:
                raise
            entry = _error_entry(team_id, str(exc))
        if meta_fn is not None:
            entry.update(meta_fn(team_id))
        entries.append(entry)

    corpus = {
        'generated_at': _isoformat(generated_at or utc_now_naive()),
        'reference_date': _isoformat(reference_date),
        'team_ids': team_ids,
        'include_unpublishable': bool(include_unpublishable),
        'writer_filter': writer,
        'entries': entries,
    }
    if seeded:
        from services.coin_seeded_fixtures import MODE_SEEDED_FIXTURE_REVIEW
        # Mode marker leads the dict; non-seeded corpora are left unchanged.
        corpus = {'mode': MODE_SEEDED_FIXTURE_REVIEW, **corpus}
    return corpus


def render_markdown(corpus: dict) -> str:
    """Render a human-readable Markdown review of a corpus dict."""
    mode = corpus.get('mode')
    lines = ['# COIN Story Corpus', '']
    if mode:
        lines += [f'Mode: {mode}', '']
        from services.coin_seeded_fixtures import (
            MODE_SEEDED_FIXTURE_REVIEW,
            SEEDED_REVIEW_WARNING,
        )
        if mode == MODE_SEEDED_FIXTURE_REVIEW:
            lines += [f'> {SEEDED_REVIEW_WARNING}', '']
    lines += [
        f"Generated at: {corpus.get('generated_at') or 'unknown'}",
        f"Reference date: {corpus.get('reference_date') or 'none'}",
        f"Teams: {', '.join(str(t) for t in corpus.get('team_ids', []))}",
        '',
    ]

    for entry in corpus.get('entries', []):
        team_id = entry.get('team_id')
        label = TEAM_LABELS.get(team_id)
        header = f'## Team {team_id}'
        if label:
            header += f' — {label}'
        lines += [header, '']

        if entry.get('fixture_name'):
            lines += [
                f"Fixture: {entry['fixture_name']}",
                f"Expected primary story: {entry.get('expected_primary_story')}",
            ]

        if entry.get('error'):
            lines += [f"Error: {entry['error']}", '']
            continue

        lines += [
            f"Publishable: {entry.get('publishable')}",
            f"Publish reason: {entry.get('publish_reason')}",
            f"Confidence: {entry.get('confidence')}",
            f"Primary story: {entry.get('primary_story')}",
            f"Recommended surface: {entry.get('recommended_surface')}",
            f"Safe time context: {entry.get('safe_time_context')}",
            '',
        ]

        drafts_by_writer = {d.get('writer'): d for d in entry.get('drafts', [])}
        for writer_name, title in _MARKDOWN_WRITERS:
            lines += [f'### {title}', '']
            draft = drafts_by_writer.get(writer_name)
            if not draft:
                lines += ['No draft rendered.', '']
                continue
            lines += [f"**{draft.get('headline', '')}**", '', draft.get('body', ''), '']
            observations = draft.get('observations') or []
            if observations:
                lines += ['Why BaseballOS sees it:']
                lines += [f'- {line}' for line in observations]
                lines += ['']
            evidence = draft.get('evidence') or []
            if evidence:
                lines += ['Evidence:']
                lines += [f'- {line}' for line in evidence]
                lines += ['']

    return '\n'.join(lines)


def write_corpus_json(corpus: dict, path, *, pretty=False) -> None:
    """Write the corpus to a local JSON review artifact."""
    with open(path, 'w', encoding='utf-8') as handle:
        if pretty:
            json.dump(corpus, handle, indent=2, sort_keys=True)
        else:
            json.dump(corpus, handle, sort_keys=True)


def write_corpus_markdown(corpus: dict, path) -> None:
    """Write the corpus to a local Markdown review artifact."""
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(render_markdown(corpus))
