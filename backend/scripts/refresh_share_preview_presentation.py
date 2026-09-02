#!/usr/bin/env python3
"""Refresh checked-in share HTML presentation without reading mutable baseball data.

The checked-in pages are already frozen public projections. This migration reads
only their immutable metadata/body receipts, renders the current static template,
and proves the meaning-bearing receipts did not change before writing a file.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from collections import Counter
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.mlb_club_directory import MLB_CLUBS
from services.share_artifact_previews import (
    REPRESENTATION,
    _date_presentation,
    _destination_label,
    render_invalid_share_html,
    render_share_artifact_html,
)


META_PATTERN = re.compile(
    r'<meta\s+name="(?P<name>[^"]+)"\s+content="(?P<value>[^"]*)"\s*/>'
)
OG_PATTERN = re.compile(
    r'<meta\s+property="(?P<name>og:[^"]+)"\s+content="(?P<value>[^"]*)"\s*/>'
)
CANONICAL_PATTERN = re.compile(r'<link\s+rel="canonical"\s+href="(?P<value>[^"]*)"\s*/>')

TEAM_NAMES = {club.abbreviation: club.team_name for club in MLB_CLUBS}
SUPPORTED_ARTIFACT_TYPES = {'team_state', 'since_yesterday_change'}
SEMANTIC_META_KEYS = (
    'baseballos:representation',
    'baseballos:public-id',
    'baseballos:artifact-type',
    'baseballos:team',
    'baseballos:team-state',
    'baseballos:live-destination',
    'baseballos:data-through',
    'baseballos:generated-at',
    'baseballos:published-at',
    'baseballos:snapshot-id',
    'baseballos:sync-run-id',
    'baseballos:schema-version',
    'baseballos:render-version',
    'baseballos:payload-version',
)
SEMANTIC_OG_KEYS = ('og:title', 'og:description', 'og:url', 'og:image')


def _named_metadata(text):
    return {
        match.group('name'): html.unescape(match.group('value'))
        for match in META_PATTERN.finditer(text)
    }


def _open_graph(text):
    return {
        match.group('name'): html.unescape(match.group('value'))
        for match in OG_PATTERN.finditer(text)
    }


def _canonical(text):
    match = CANONICAL_PATTERN.search(text)
    return html.unescape(match.group('value')) if match else None


def semantic_receipt(text):
    metadata = _named_metadata(text)
    open_graph = _open_graph(text)
    return {
        'metadata': {key: metadata.get(key) for key in SEMANTIC_META_KEYS},
        'open_graph': {key: open_graph.get(key) for key in SEMANTIC_OG_KEYS},
        'canonical': _canonical(text),
    }


def preview_from_generated_html(text, *, path=None):
    """Recover only already-published fields from an existing generated page."""
    metadata = _named_metadata(text)
    open_graph = _open_graph(text)
    artifact_type = metadata.get('baseballos:artifact-type')
    if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
        raise ValueError(f'{path or "generated page"}: unsupported artifact type {artifact_type!r}')

    public_id = metadata.get('baseballos:public-id')
    team_abbreviation = metadata.get('baseballos:team')
    team_name = TEAM_NAMES.get(team_abbreviation)
    title = open_graph.get('og:title')
    description = open_graph.get('og:description')
    canonical_url = _canonical(text)
    live_destination = metadata.get('baseballos:live-destination')
    data_through = metadata.get('baseballos:data-through')
    required = {
        'public_id': public_id,
        'team': team_abbreviation,
        'team_name': team_name,
        'title': title,
        'description': description,
        'canonical': canonical_url,
        'live_destination': live_destination,
        'data_through': data_through,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(f'{path or "generated page"}: missing frozen fields {missing}')

    if artifact_type == 'since_yesterday_change':
        primary_claim = title
        supporting_copy = [description] if description.casefold() != title.casefold() else []
    else:
        primary_claim = description
        supporting_copy = []
    date_presentation = _date_presentation(data_through)
    copy_text = ' '.join([primary_claim, *supporting_copy]).casefold()
    date_embedded = bool(
        date_presentation
        and any(
            value and value.casefold() in copy_text
            for value in (date_presentation.get('current'), date_presentation.get('label'))
        )
    )
    return {
        'public_id': public_id,
        'artifact_type': artifact_type,
        'schema_version': metadata.get('baseballos:schema-version'),
        'render_version': metadata.get('baseballos:render-version'),
        'payload_version': metadata.get('baseballos:payload-version'),
        'representation': metadata.get('baseballos:representation') or REPRESENTATION,
        'title': title,
        'description': description,
        'canonical_url': canonical_url,
        'og_image': open_graph.get('og:image'),
        'twitter_card': 'summary_large_image',
        'team_abbreviation': team_abbreviation,
        'team_name': team_name,
        'team_state_label': metadata.get('baseballos:team-state'),
        'evidence': [],
        'historical_context': None,
        'data_through': data_through,
        'previous_data_through': None,
        'date_presentation': date_presentation,
        'date_embedded_in_copy': date_embedded,
        'primary_claim': primary_claim,
        'supporting_copy': supporting_copy,
        'generated_at': metadata.get('baseballos:generated-at'),
        'published_at': metadata.get('baseballos:published-at'),
        'snapshot_id': metadata.get('baseballos:snapshot-id'),
        'sync_run_id': metadata.get('baseballos:sync-run-id'),
        'live_destination_path': live_destination,
        'live_destination_label': _destination_label(live_destination, team_name),
    }


def refresh_page(path, *, write=True):
    original = path.read_text(encoding='utf-8')
    preview = preview_from_generated_html(original, path=path)
    refreshed = render_share_artifact_html(preview)
    before = semantic_receipt(original)
    after = semantic_receipt(refreshed)
    if before != after:
        raise ValueError(f'{path}: semantic receipt changed during presentation refresh')
    for frozen_text in (preview['title'], preview['description']):
        if html.escape(frozen_text) not in refreshed:
            raise ValueError(f'{path}: frozen claim text is absent from refreshed static body')
    changed = original != refreshed
    if changed and write:
        path.write_text(refreshed, encoding='utf-8')
    return preview['artifact_type'], changed


def refresh_corpus(output_root, *, write=True):
    output_root = Path(output_root)
    pages = sorted((output_root / 'share').glob('*/index.html'))
    if not pages:
        raise ValueError(f'no generated share pages found below {output_root}')
    type_counts = Counter()
    changed = 0
    for path in pages:
        artifact_type, page_changed = refresh_page(path, write=write)
        type_counts[artifact_type] += 1
        changed += int(page_changed)

    fallback = output_root / 'share-404.html'
    if fallback.is_file():
        refreshed_fallback = render_invalid_share_html()
        fallback_changed = fallback.read_text(encoding='utf-8') != refreshed_fallback
        if fallback_changed and write:
            fallback.write_text(refreshed_fallback, encoding='utf-8')
    else:
        fallback_changed = False
    return {
        'pages': len(pages),
        'changed': changed,
        'semantic_equal': len(pages),
        'artifact_types': dict(sorted(type_counts.items())),
        'fallback_changed': fallback_changed,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', default='frontend/public')
    parser.add_argument('--check', action='store_true', help='prove the refresh without writing')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    summary = refresh_corpus(args.output_root, write=not args.check)
    mode = 'checked' if args.check else 'refreshed'
    print(
        f'Share preview corpus {mode}: pages={summary["pages"]} '
        f'changed={summary["changed"]} semantic_equal={summary["semantic_equal"]} '
        f'artifact_types={summary["artifact_types"]} '
        f'fallback_changed={summary["fallback_changed"]}'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
