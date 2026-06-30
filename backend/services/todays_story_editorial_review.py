"""Live stored-slate editorial review for Today's Story completed-game copy.

This module is read-only: it reads stored CompletedGameContext rows, runs the
existing COIN inspection/story-writer path, and formats a local Markdown review
artifact. It does not sync, mutate snapshots, publish, or change selection.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import re
from typing import Any

from services.coin_story_inspection import inspect_team_story
from services.editorial_voice_contract_v1 import find_editorial_violations
from services.intelligence_surface_service import (
    build_today_lead_story,
    resolve_default_reference_date,
)
from utils.time import utc_now_naive


ARTIFACT_PATH = 'artifacts/todays_story_editorial_review_E2C5C_live.md'
IMPOSSIBLE_INNINGS_PATTERN = re.compile(r'\b\d+\.[367]\b')
SOURCE_PATH_HOMEPAGE = (
    'current stored CompletedGameContext rows -> build_today_lead_story '
    '(on-demand, no snapshot write)'
)
SOURCE_PATH_ROW = (
    'CompletedGameContext row -> inspect_team_story -> existing story writers'
)


def build_todays_story_editorial_review(
    *,
    app=None,
    reference_date=None,
    current_date=None,
    candidate_contexts=None,
    inspect_fn=None,
    generated_at=None,
) -> dict[str, Any]:
    """Build a deterministic review payload from current stored context rows."""

    def _run():
        ref_date, contexts, snapshot_present, live_data_error = _resolve_contexts(
            reference_date=reference_date,
            current_date=current_date,
            candidate_contexts=candidate_contexts,
        )
        ref_iso = _isoformat(ref_date)
        contexts = [_context_dict(ctx) for ctx in contexts]

        inspect = inspect_fn or inspect_team_story
        lead_response = build_today_lead_story(
            reference_date=ref_iso,
            candidate_contexts=contexts,
            inspect_fn=inspect,
        )
        entries = [_inspect_context(ctx, ref_iso, inspect) for ctx in contexts]

        scans = _scan_entries(entries)
        headline_summary = _headline_reuse_summary(entries)
        repetition_summary = _same_beat_repetition_summary(entries)
        story_counts = Counter(
            (entry.get('primary_story') or entry.get('context_story_tag') or 'unknown')
            for entry in entries
        )

        publishable = sum(1 for entry in entries if entry.get('publishable') is True)
        unpublishable = sum(1 for entry in entries if entry.get('publishable') is not True)
        rendered_drafts = sum(len(entry.get('drafts') or []) for entry in entries)

        return {
            'artifact': ARTIFACT_PATH,
            'generated_at': _isoformat(generated_at or utc_now_naive()),
            'reference_date': ref_iso,
            'source_mode': 'current stored DB data only; no sync started',
            'generation_path_used': [
                'services.todays_story_editorial_review.build_todays_story_editorial_review',
                'services.intelligence_surface_service.build_today_lead_story',
                'services.coin_story_inspection.inspect_team_story',
                'story_writers::{TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter}',
            ],
            'snapshot_present_for_reference_date': snapshot_present,
            'live_data_error': live_data_error,
            'completed_game_context_rows_reviewed': len(contexts),
            'completed_game_publishable_stories': publishable,
            'completed_game_fallback_or_unpublishable_rows': unpublishable,
            'completed_game_rendered_drafts': rendered_drafts,
            'primary_story_distribution': dict(sorted(story_counts.items())),
            'homepage_response': lead_response,
            'homepage_lead_story': lead_response.get('lead_story') if lead_response else None,
            'homepage_status': (lead_response or {}).get('status'),
            'homepage_empty_reason': (lead_response or {}).get('empty_reason'),
            'homepage_errors': (lead_response or {}).get('errors'),
            'homepage_publishable_candidates': (lead_response or {}).get('publishable_candidates'),
            'homepage_candidates_considered': (lead_response or {}).get('candidates_considered'),
            'entries': entries,
            'banned_language_scan': scans['banned_language_scan'],
            'impossible_innings_scan': scans['impossible_innings_scan'],
            'headline_reuse_summary': headline_summary,
            'same_beat_repetition_summary': repetition_summary,
        }

    if app is not None:
        with app.app_context():
            return _run()
    return _run()


def write_todays_story_editorial_review(report: dict[str, Any], path: str | Path) -> Path:
    """Write the Markdown review artifact and return its path."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_todays_story_editorial_review_markdown(report), encoding='utf-8')
    return output


def render_todays_story_editorial_review_markdown(report: dict[str, Any]) -> str:
    """Render a readable Markdown artifact with exact public draft wording."""

    lines: list[str] = [
        "# Today's Story Editorial Review Corpus - E2C-5C Live",
        '',
        'Read-only export of the current stored homepage-visible Today\'s Story / '
        'completed-game story writer path after the final E2C-5C polish pass.',
        '',
        '## Export Metadata',
        '',
        _json_block(_metadata(report)),
        '',
        '## Editorial Banned-Language Scan',
        '',
        _scan_status_line(report.get('banned_language_scan'), 'banned language'),
        '',
        '## Impossible Innings Scan',
        '',
        _scan_status_line(report.get('impossible_innings_scan'), 'impossible innings notation'),
        '',
        '## Headline Reuse Summary',
        '',
        _json_block(report.get('headline_reuse_summary') or {}),
        '',
        '## Same-Beat Repetition / Swap-Test Summary',
        '',
        _json_block(report.get('same_beat_repetition_summary') or {}),
        '',
        '## Homepage Lead Story',
        '',
    ]

    lead = report.get('homepage_lead_story')
    if lead:
        lines.extend(_homepage_lines(lead))
    else:
        lines.append('No homepage lead story rendered.')
        lines.append('')

    entries = report.get('entries') or []
    slate_label = report.get('reference_date') or 'an unresolved reference date'
    lines.extend([
        '## Completed-Game Story Corpus',
        '',
        (
            f"This section contains {len(entries)} current stored completed-game "
            f"contexts for {slate_label}. Each row was rendered "
            'through inspect_team_story with the existing writer targets only.'
        ),
        '',
    ])
    for index, entry in enumerate(entries, start=1):
        lines.extend(_entry_lines(index, entry))

    return '\n'.join(lines).rstrip() + '\n'


def _resolve_contexts(*, reference_date, current_date, candidate_contexts):
    if candidate_contexts is not None:
        contexts = [_context_dict(ctx) for ctx in candidate_contexts if ctx]
        ref = reference_date
        if ref is None and contexts:
            ref = contexts[0].get('game_date')
        return ref, contexts, False, None

    from models.completed_game_context import CompletedGameContext

    try:
        ref = resolve_default_reference_date(reference_date, current_date)
        if ref is None:
            return None, [], False, None
        rows = (
            CompletedGameContext.query
            .filter_by(game_date=ref)
            .order_by(CompletedGameContext.team_id.asc(),
                      CompletedGameContext.game_pk.asc())
            .all()
        )
        return ref, rows, _snapshot_present(ref), None
    except Exception as exc:  # noqa: BLE001 - artifact records read failures
        return reference_date, [], False, _error_summary(exc)


def _snapshot_present(reference_date) -> bool:
    try:
        from services.intelligence_surface_snapshot import read_snapshot

        return read_snapshot(reference_date) is not None
    except Exception:  # noqa: BLE001 - artifact metadata only
        return False


def _inspect_context(ctx: dict[str, Any], reference_date, inspect_fn) -> dict[str, Any]:
    team_id = ctx.get('team_id')
    base = {
        'team_id': team_id,
        'game_pk': ctx.get('game_pk'),
        'game_date': ctx.get('game_date'),
        'context_story_tag': ctx.get('bullpen_story_tag'),
        'context_confidence': ctx.get('confidence'),
        'source_path': SOURCE_PATH_ROW,
        'completed_game_context': ctx,
        'export_error': None,
    }
    try:
        result = inspect_fn(
            team_id,
            app=None,
            reference_date=reference_date,
            completed_game_context=ctx,
        )
    except Exception as exc:  # noqa: BLE001 - keep full-slate export alive
        base.update({
            'publishable': None,
            'publish_reason': None,
            'confidence': None,
            'story_priority': None,
            'game_importance': None,
            'recommended_surface': None,
            'primary_story': None,
            'writer_targets': [],
            'package': None,
            'drafts': [],
            'export_error': str(exc),
        })
        return base

    package = result.get('package') or {}
    completed = package.get('completed_game_context') or ctx
    base.update({
        'team_id': result.get('team_id', team_id),
        'game_pk': result.get('game_pk', ctx.get('game_pk')),
        'publishable': result.get('publishable'),
        'publish_reason': result.get('publish_reason'),
        'confidence': result.get('confidence'),
        'story_priority': result.get('story_priority'),
        'game_importance': result.get('game_importance'),
        'recommended_surface': result.get('recommended_surface'),
        'safe_time_context': result.get('safe_time_context'),
        'primary_story': package.get('primary_story'),
        'writer_targets': result.get('writer_targets') or [],
        'package': package,
        'drafts': result.get('drafts') or [],
        'team_label': completed.get('team_name') or f"Team {result.get('team_id', team_id)}",
        'opponent_name': completed.get('opponent_name'),
    })
    return base


def _scan_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    banned = []
    innings = []
    for entry in entries:
        for draft in entry.get('drafts') or []:
            text = draft.get('rendered_text') or ''
            for violation in find_editorial_violations(text):
                banned.append({
                    'team_id': entry.get('team_id'),
                    'game_pk': entry.get('game_pk'),
                    'writer': draft.get('writer'),
                    **violation,
                })
            for match in IMPOSSIBLE_INNINGS_PATTERN.finditer(text):
                innings.append({
                    'team_id': entry.get('team_id'),
                    'game_pk': entry.get('game_pk'),
                    'writer': draft.get('writer'),
                    'match': match.group(0),
                    'start': match.start(),
                })
    return {
        'banned_language_scan': {
            'scope': 'rendered public completed-game draft text only',
            'status': 'pass' if not banned else 'warn',
            'violation_count': len(banned),
            'violations': banned,
        },
        'impossible_innings_scan': {
            'scope': 'rendered public completed-game draft text only',
            'status': 'pass' if not innings else 'warn',
            'violation_count': len(innings),
            'violations': innings,
        },
    }


def _error_summary(exc: Exception) -> str:
    message = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    return f'{exc.__class__.__name__}: {message}'


def _headline_reuse_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(
        draft.get('headline')
        for entry in entries
        for draft in (entry.get('drafts') or [])
        if draft.get('headline')
    )
    return {
        'headline_counts': dict(sorted(counter.items())),
        'max_reuse_count': max(counter.values()) if counter else 0,
        'reused_headlines': {
            headline: count for headline, count in sorted(counter.items())
            if count > 1
        },
    }


def _same_beat_repetition_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_beat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if entry.get('publishable') is not True:
            continue
        draft = _draft_by_writer(entry, 'team_story')
        if not draft:
            continue
        beat = entry.get('primary_story') or entry.get('context_story_tag') or 'unknown'
        by_beat[beat].append({
            'team_id': entry.get('team_id'),
            'game_pk': entry.get('game_pk'),
            'headline': draft.get('headline'),
            'template_key': _template_key(draft.get('body') or ''),
        })

    beat_summaries = {}
    duplicate_groups = []
    for beat, items in sorted(by_beat.items()):
        counter = Counter(item['template_key'] for item in items)
        duplicates = [
            {
                'template_key': key,
                'count': count,
                'teams': [
                    item['team_id'] for item in items
                    if item['template_key'] == key
                ],
            }
            for key, count in sorted(counter.items())
            if count > 1
        ]
        beat_summaries[beat] = {
            'story_count': len(items),
            'unique_template_count': len(counter),
            'duplicate_template_count': sum(item['count'] for item in duplicates),
        }
        duplicate_groups.extend({'beat': beat, **item} for item in duplicates)

    return {
        'scope': 'publishable team_story completed-game bodies, stripped names/numbers',
        'beat_summaries': beat_summaries,
        'duplicate_groups': duplicate_groups,
        'status': 'pass' if not duplicate_groups else 'review',
    }


def _template_key(text: str) -> str:
    text = re.sub(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', 'NAME', text)
    text = re.sub(r'\b\d+(?:\.\d+)?\b', 'NUM', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


def _metadata(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            'artifact',
            'generated_at',
            'reference_date',
            'source_mode',
            'generation_path_used',
            'snapshot_present_for_reference_date',
            'live_data_error',
            'completed_game_context_rows_reviewed',
            'completed_game_publishable_stories',
            'completed_game_fallback_or_unpublishable_rows',
            'completed_game_rendered_drafts',
            'primary_story_distribution',
            'homepage_status',
            'homepage_empty_reason',
            'homepage_errors',
            'homepage_publishable_candidates',
            'homepage_candidates_considered',
        )
    }


def _homepage_lines(lead: dict[str, Any]) -> list[str]:
    package = lead.get('package') or {}
    metadata = {
        'team_id': lead.get('team_id'),
        'game_pk': lead.get('game_pk'),
        'source_path': SOURCE_PATH_HOMEPAGE,
        'selection': lead.get('selection'),
        'story_type': package.get('primary_story'),
        'beat': package.get('primary_story'),
        'supporting_context_values': _supporting_context_values(package),
    }
    lines = ['### Lead Metadata', '', _json_block(metadata), '']
    drafts = lead.get('drafts') or {}
    for writer, draft in drafts.items():
        lines.extend(_draft_lines(f'Homepage Draft: {writer}', draft))
    return lines


def _entry_lines(index: int, entry: dict[str, Any]) -> list[str]:
    label = entry.get('team_label') or f"Team {entry.get('team_id')}"
    title = (
        f"## Completed-Game Story {index}: "
        f"{label} "
        f"({entry.get('team_id')})"
    )
    package = entry.get('package') or {}
    metadata = {
        'team_id': entry.get('team_id'),
        'game_pk': entry.get('game_pk'),
        'game_date': entry.get('game_date'),
        'opponent_name': entry.get('opponent_name'),
        'source_path': entry.get('source_path'),
        'story_type': entry.get('primary_story') or entry.get('context_story_tag'),
        'beat': entry.get('primary_story') or entry.get('context_story_tag'),
        'confidence': entry.get('confidence') or entry.get('context_confidence'),
        'story_priority': entry.get('story_priority'),
        'game_importance': entry.get('game_importance'),
        'publishable': entry.get('publishable'),
        'publish_reason': entry.get('publish_reason'),
        'recommended_surface': entry.get('recommended_surface'),
        'safe_time_context': entry.get('safe_time_context'),
        'writer_targets': entry.get('writer_targets'),
        'fallback_or_unpublishable': entry.get('publishable') is not True,
        'export_error': entry.get('export_error'),
        'supporting_context_values': _supporting_context_values(package),
    }
    lines = [title, '', '### Story Metadata', '', _json_block(metadata), '']
    drafts = entry.get('drafts') or []
    if not drafts:
        lines.extend(['No draft rendered.', ''])
        return lines
    for draft in drafts:
        lines.extend(_draft_lines(f"Draft: {draft.get('writer')}", draft))
    return lines


def _draft_lines(title: str, draft: dict[str, Any]) -> list[str]:
    return [
        f'### {title}',
        '',
        'Headline:',
        '```',
        draft.get('headline') or '',
        '```',
        'Body:',
        '```',
        draft.get('body') or '',
        '```',
        'What BaseballOS noticed / observations:',
        '```',
        _bullet_text(draft.get('observations') or []),
        '```',
        'Evidence:',
        '```',
        _bullet_text(draft.get('evidence') or []),
        '```',
        'Exact rendered text:',
        '```',
        draft.get('rendered_text') or '',
        '```',
        '',
    ]


def _supporting_context_values(package: dict[str, Any]) -> dict[str, Any]:
    return {
        key: package.get(key)
        for key in (
            'completed_game_context',
            'narrative_context',
            'availability_snapshot',
            'workload_snapshot',
            'bullpen_snapshot',
            'evidence_blocks',
        )
        if package.get(key) is not None
    }


def _draft_by_writer(entry: dict[str, Any], writer: str) -> dict[str, Any] | None:
    for draft in entry.get('drafts') or []:
        if draft.get('writer') == writer:
            return draft
    return None


def _scan_status_line(scan: dict[str, Any] | None, label: str) -> str:
    scan = scan or {}
    status = scan.get('status') or 'unknown'
    count = scan.get('violation_count')
    if count:
        return f"Status: {status} - {count} {label} violation(s) found.\n\n{_json_block(scan)}"
    return f'Status: {status} - no {label} violations found.'


def _bullet_text(items: list[Any]) -> str:
    if not items:
        return '(none)'
    return '\n'.join(f'- {item}' for item in items)


def _json_block(value: Any) -> str:
    return '```json\n' + json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n```'


def _context_dict(ctx: Any) -> dict[str, Any]:
    if isinstance(ctx, dict):
        return dict(ctx)
    to_dict = getattr(ctx, 'to_dict', None)
    if callable(to_dict):
        result = to_dict()
        return result if isinstance(result, dict) else {}
    return {}


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, 'isoformat', None)
    return isoformat() if callable(isoformat) else str(value)


__all__ = [
    'ARTIFACT_PATH',
    'IMPOSSIBLE_INNINGS_PATTERN',
    'build_todays_story_editorial_review',
    'render_todays_story_editorial_review_markdown',
    'write_todays_story_editorial_review',
]
